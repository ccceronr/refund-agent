"""The agent flow as a LangGraph graph (design §5; R-04…R-13).

A sequential pipeline with one parallel fan-out (evidence), a typed decision layer (Jev,
with Haiku as fallback) and a deterministic supervisor (the rules engine) that owns the
outcome. Models only read and write text; they never call tools that write.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from itertools import pairwise
from typing import Any, Protocol

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.agents.decider import Decider
from app.agents.errors import DATA_ERRORS, ModelUnavailable
from app.agents.guard import check_draft
from app.agents.proposal import build_plan
from app.agents.questions import fee_question, policy_question, screening_questions
from app.agents.state import Draft, Exit, PolicyQuote, RunState, Screening
from app.agents.steps import StepTracker
from app.agents.templates import FeeFacts, TemplateContext, render_template, template_key
from app.agents.writer import ReplyFacts, WrittenReply
from app.core.config import Settings
from app.rules.fees import fee_type, plain_name
from app.rules.model import Evaluation, ReasonCode, Recommendation, Thresholds, TypedAnswer
from app.rules.outcome import evaluate
from app.rules.texts import day, money
from app.services.finalize import Finalizer
from app.tools.evidence import fee_lookback_start, refund_lookback_start, to_rule_input
from app.tools.queries import (
    find_fee_candidates,
    get_day_postings,
    get_member_accounts,
    get_member_standing,
    get_refund_history,
    load_case,
    search_policy,
)
from app.tools.recording import ToolRecorder
from app.tools.schemas import CaseContext, FeeCandidate, LedgerTransaction

POLICY_PICK_MIN_CONFIDENCE = 0.6  # design §6.1

# design §6.1: one full-text query per reason code.
POLICY_QUERIES = {
    ReasonCode.ELIGIBLE: "refund overdraft fee same day deposit posting order",
    ReasonCode.LIMIT_REACHED: "refund limit per member 12 months",
    ReasonCode.OUT_OF_WINDOW: "request within 60 days of fee",
    ReasonCode.NOT_GOOD_STANDING: "good standing fraud collections refund",
    ReasonCode.NO_QUALIFYING_REASON: "qualifying reason refund deposit covered",
    ReasonCode.ALREADY_REFUNDED: "fee refunded once",
    ReasonCode.FEE_TYPE_NOT_COVERED: "fees not covered staff discretion",
}
# The `decision` Jev reads when picking the passage that states the rule (design §6.1).
DECISION_SENTENCES = {
    ReasonCode.ELIGIBLE: "Refund the fee: a same-day deposit would have covered the payment.",
    ReasonCode.LIMIT_REACHED: "No refund: the member already used every refund in 12 months.",
    ReasonCode.OUT_OF_WINDOW: "No refund: the member asked more than 60 days after the fee.",
    ReasonCode.NOT_GOOD_STANDING: "No refund: the member is not in good standing.",
    ReasonCode.NO_QUALIFYING_REASON: "No refund: no same-day deposit covered the payment.",
    ReasonCode.ALREADY_REFUNDED: "No refund: this fee was already refunded.",
    ReasonCode.FEE_TYPE_NOT_COVERED: "Staff decide: this kind of fee isn't covered by the policy.",
}
# The check whose text explains a NO_REFUND reason to the writer.
REASON_CHECK = {
    ReasonCode.ALREADY_REFUNDED: "BR-05",
    ReasonCode.OUT_OF_WINDOW: "BR-04",
    ReasonCode.NOT_GOOD_STANDING: "BR-06",
    ReasonCode.NO_QUALIFYING_REASON: "BR-02",
    ReasonCode.LIMIT_REACHED: "BR-03",
}


class ReplyWriter(Protocol):
    async def write(self, facts: ReplyFacts) -> WrittenReply: ...


@dataclass(frozen=True)
class FlowDeps:
    settings: Settings
    thresholds: Thresholds
    ro_engine: AsyncEngine  # agent_ro: the flow can only read (R-31)
    decider: Decider
    writer: ReplyWriter
    tracker: StepTracker
    finalizer: Finalizer


class Flow:
    def __init__(self, deps: FlowDeps) -> None:
        self._d = deps

    async def load_case(self, state: RunState) -> dict[str, Any]:
        async with self._d.tracker.step("load_case", "tool", "db") as step:
            recorder = ToolRecorder()
            try:
                case = await recorder.run(
                    "load_case", self._read(lambda c: load_case(c, state.case_id))
                )
            except DATA_ERRORS:
                step.fail(ReasonCode.DATA_UNAVAILABLE.value)
                return {"exit": Exit("manual", ReasonCode.DATA_UNAVAILABLE)}
            finally:
                step.add_tool_calls(recorder)
            return {"case": case}

    async def screen(self, state: RunState) -> dict[str, Any]:
        case = _required(state.case)
        async with self._d.tracker.step("screen", "decision", "jev") as step:
            try:
                decisions = await self._d.decider.decide(
                    self._screening_text(case), screening_questions()
                )
            except ModelUnavailable:
                step.fail(ReasonCode.AI_UNAVAILABLE.value)
                return {"exit": Exit("manual", ReasonCode.AI_UNAVAILABLE)}
            step.add_decisions(decisions)
            intent, language = decisions.choice("intent"), decisions.choice("language")
            screening = Screening(
                intent=intent.choice,
                intent_answer=TypedAnswer(decisions.source, intent.confidence),
                injection_probability=decisions.noul("injection").noul,
                language="es" if language.choice == "es" else "en",
                language_answer=TypedAnswer(decisions.source, language.confidence),
                tone=decisions.choice("tone").choice,  # type: ignore[arg-type]  # validated options
            )
            step.output.update(intent=screening.intent, injection=screening.injection_probability)
            return {"screening": screening, "exit": self._screening_exit(screening)}

    def _screening_exit(self, screening: Screening) -> Exit | None:
        """design §5.2 route_screen (R-05, R-06)."""
        settings = self._d.settings
        if screening.injection_probability >= settings.injection_threshold:
            return Exit("manual", ReasonCode.INJECTION_SUSPECTED)
        confident = screening.intent_answer.confidence >= settings.decision_min_confidence
        if screening.intent == "other_banking" and confident:
            return Exit("not_refund")
        if screening.intent != "fee_refund" or not confident:
            return Exit("manual", ReasonCode.INTENT_UNCLEAR)
        return None

    async def gather_evidence(self, state: RunState) -> dict[str, Any]:
        case = _required(state.case)
        as_of, member = case.as_of.date(), case.member_id
        limits = self._d.thresholds
        async with self._d.tracker.step("gather_evidence", "tool", "db") as step:
            recorder = ToolRecorder()
            fees_since = fee_lookback_start(as_of, limits)
            refunds_since = refund_lookback_start(as_of, limits)

            async def candidates_query(c: AsyncConnection) -> list[FeeCandidate]:
                return await find_fee_candidates(c, member, since=fees_since, until=as_of)

            async def refunds_query(c: AsyncConnection) -> list[LedgerTransaction]:
                return await get_refund_history(c, member, since=refunds_since, until=as_of)

            try:
                accounts, candidates, standing, refunds = await asyncio.gather(
                    recorder.run(
                        "get_member_accounts", self._read(lambda c: get_member_accounts(c, member))
                    ),
                    recorder.run("find_fee_candidates", self._read(candidates_query)),
                    recorder.run(
                        "get_member_standing", self._read(lambda c: get_member_standing(c, member))
                    ),
                    recorder.run("get_refund_history", self._read(refunds_query)),
                )
            except DATA_ERRORS:
                step.fail(ReasonCode.DATA_UNAVAILABLE.value)
                return {"exit": Exit("manual", ReasonCode.DATA_UNAVAILABLE)}
            finally:
                step.add_tool_calls(recorder)
            step.output["fee_candidates"] = len(candidates)
            return {
                "accounts": accounts,
                "candidates": candidates,
                "standing": standing,
                "refunds": refunds,
            }

    async def identify_fee(self, state: RunState) -> dict[str, Any]:
        """R-08: 0 → NO_FEE_FOUND; 1 → that fee; more → Jev picks, or AMBIGUOUS_FEE."""
        candidates = state.candidates
        async with self._d.tracker.step("identify_fee", "decision", "none") as step:
            if not candidates:
                return {"exit": Exit("manual", ReasonCode.NO_FEE_FOUND)}
            if len(candidates) == 1:
                return {"fee": candidates[0], "fee_choice": None}
            try:
                decisions = await self._d.decider.decide(
                    *self._fee_question(_required(state.case), candidates)
                )
            except ModelUnavailable:
                step.fail(ReasonCode.AI_UNAVAILABLE.value)
                return {"exit": Exit("manual", ReasonCode.AI_UNAVAILABLE)}
            step.add_decisions(decisions)
            answer = decisions.choice("fee")
            if (
                answer.choice == "unclear"
                or answer.confidence < self._d.settings.decision_min_confidence
            ):
                return {"exit": Exit("manual", ReasonCode.AMBIGUOUS_FEE)}
            fee = candidates[int(answer.choice.removeprefix("fee_")) - 1]
            return {"fee": fee, "fee_choice": TypedAnswer(decisions.source, answer.confidence)}

    def _fee_question(self, case: CaseContext, candidates: list[FeeCandidate]) -> tuple[Any, Any]:
        labels = {f"fee_{n}": _fee_label(c) for n, c in enumerate(candidates, 1)}
        as_of = case.as_of.date()
        state = {
            "message": self._member_text(case),
            "request_date": f"{day(as_of)}, {as_of.year}",
            "fees": labels,
        }
        return state, fee_question(labels)

    async def day_postings(self, state: RunState) -> dict[str, Any]:
        fee = _required(state.fee).transaction
        async with self._d.tracker.step("day_postings", "tool", "db") as step:
            recorder = ToolRecorder()
            try:
                postings = await recorder.run(
                    "get_day_postings",
                    self._read(lambda c: get_day_postings(c, fee.sub_account_id, fee.date)),
                )
            except DATA_ERRORS:
                step.fail(ReasonCode.DATA_UNAVAILABLE.value)
                return {"exit": Exit("manual", ReasonCode.DATA_UNAVAILABLE)}
            finally:
                step.add_tool_calls(recorder)
            return {"day_postings": postings}

    async def evaluate_rules(self, state: RunState) -> dict[str, Any]:
        case, fee = _required(state.case), _required(state.fee)
        async with self._d.tracker.step("evaluate_rules", "rules") as step:
            rule_input = to_rule_input(
                first_name=case.first_name,
                as_of=case.as_of.date(),
                fee=fee,
                day_postings=state.day_postings,
                refunds=state.refunds,
                standing=_required(state.standing),
            )
            evaluation = evaluate(rule_input, self._d.thresholds)
            step.output.update(
                recommendation=evaluation.recommendation.value,
                reason_code=evaluation.reason_code.value,
            )
            return {"evaluation": evaluation}

    async def find_policy(self, state: RunState) -> dict[str, Any]:
        """R-10: an exact passage, picked by Jev from the top FTS hits. Never blocks the flow."""
        reason = _required(state.evaluation).reason_code
        async with self._d.tracker.step("find_policy", "retrieval", "db") as step:
            try:
                hits = await self._read(lambda c: search_policy(c, POLICY_QUERIES[reason]))
            except DATA_ERRORS:
                step.output["picked"] = "none_search_failed"
                return {"policy_quote": None}
            if not hits:
                return {"policy_quote": None}
            passages = {f"p{n}": hit for n, hit in enumerate(hits, 1)}
            chosen = hits[0]
            try:
                decisions = await self._d.decider.decide(
                    {
                        "decision": DECISION_SENTENCES[reason],
                        "passages": {k: h.text for k, h in passages.items()},
                    },
                    policy_question(list(passages)),
                )
                step.add_decisions(decisions)
                pick = decisions.choice("passage")
                if pick.choice in passages and pick.confidence >= POLICY_PICK_MIN_CONFIDENCE:
                    chosen = passages[pick.choice]
            except ModelUnavailable:
                step.output["picked"] = "top_search_hit"
            quote = PolicyQuote(
                chosen.passage_id, chosen.document_slug, chosen.document_title, chosen.text
            )
            return {"policy_quote": quote}

    async def draft_reply(self, state: RunState) -> dict[str, Any]:
        evaluation = _required(state.evaluation)
        async with self._d.tracker.step("draft_reply", "writer", "anthropic") as step:
            if evaluation.recommendation is Recommendation.MANUAL:
                return {"draft": Draft(self._template(state, "MANUAL"), "template")}
            try:
                reply = await self._d.writer.write(self._reply_facts(state, evaluation))
            except ModelUnavailable as error:
                step.output["template_because"] = error.reason
                return {
                    "draft": Draft(
                        self._template(
                            state, template_key(evaluation.recommendation, evaluation.reason_code)
                        ),
                        "template",
                    )
                }
            step.add_reply(reply)
            return {"draft": Draft(reply.text, "writer")}

    async def guard_output(self, state: RunState) -> dict[str, Any]:
        evaluation, draft = _required(state.evaluation), _required(state.draft)
        async with self._d.tracker.step("guard_output", "guard", "none") as step:
            if draft.source != "writer":
                return {}
            result = await check_draft(
                draft.text,
                fee_amount=evaluation.amount,
                language=_required(state.screening).language,
                recommendation=evaluation.recommendation,
                decider=self._d.decider,
                min_confidence=self._d.settings.decision_min_confidence,
            )
            if result.decisions is not None:
                step.add_decisions(result.decisions)
            step.output["failures"] = list(result.failures)
            if result.passed:
                return {"draft": Draft(draft.text, "writer", (), result.decisions)}
            key = template_key(evaluation.recommendation, evaluation.reason_code)
            return {
                "draft": Draft(
                    self._template(state, key), "template", result.failures, result.decisions
                )
            }

    async def finalize(self, state: RunState) -> dict[str, Any]:
        async with self._d.tracker.step("finalize", "rules", "db") as step:
            plan = build_plan(state, self._d.thresholds)
            outcome = await self._d.finalizer.finalize(state.case_id, state.run_id, plan)
            if outcome.refunded:
                step.label = "Refunded automatically"
            step.output.update(
                case_status=outcome.case_status, tier=outcome.tier, reason_code=outcome.reason_code
            )
            return {"outcome": outcome}

    # --- helpers ---------------------------------------------------------------------

    async def _read[R](self, query: Callable[[AsyncConnection], Awaitable[R]]) -> R:
        # One connection per query, so the evidence tools really run in parallel.
        async with self._d.ro_engine.connect() as connection:
            return await query(connection)

    def _screening_text(self, case: CaseContext) -> str:
        """The subject Luis also sees, then the member's messages (design §6.1, §8; R-41)."""
        messages = "\n".join(f"Member: {m.body}" for m in case.member_messages)
        text = f"Subject: {case.subject}\n{messages}"
        return text[: self._d.settings.max_message_chars_for_models]

    def _member_text(self, case: CaseContext) -> str:
        """The member's messages only, oldest first, truncated for the models (R-41, design §8)."""
        text = "\n".join(f"Member: {m.body}" for m in case.member_messages)
        return text[: self._d.settings.max_message_chars_for_models]

    def _reply_facts(self, state: RunState, evaluation: Evaluation) -> ReplyFacts:
        case, screening, fee = (
            _required(state.case),
            _required(state.screening),
            _required(state.fee),
        )
        reason = None
        if evaluation.recommendation is Recommendation.NO_REFUND:
            rule = REASON_CHECK[evaluation.reason_code]
            reason = next(c.text for c in evaluation.checks if c.rule == rule)
        return ReplyFacts(
            outcome="REFUND" if evaluation.recommendation is Recommendation.REFUND else "NO_REFUND",
            first_name=case.first_name,
            credit_union_name=case.credit_union_name,
            language=screening.language,
            tone=screening.tone,
            fee_name=plain_name(evaluation.fee_type),
            amount=evaluation.amount,
            fee_day=day(fee.transaction.date),
            reason=reason,
            member_message=self._member_text(case),
        )

    def _template(self, state: RunState, key: Any) -> str:
        case, evaluation, fee = (
            _required(state.case),
            _required(state.evaluation),
            _required(state.fee),
        )
        facts = FeeFacts(evaluation.fee_type, evaluation.amount, fee.transaction.date)
        context = TemplateContext(
            case.first_name, case.credit_union_name, facts, self._d.thresholds.claim_window_days
        )
        language = state.screening.language if state.screening else "en"
        return render_template(key, language, context)


def build_graph(deps: FlowDeps) -> CompiledStateGraph[RunState, Any, RunState, RunState]:
    flow = Flow(deps)
    graph = StateGraph(RunState)
    pipeline = [
        ("load_case", flow.load_case),
        ("screen", flow.screen),
        ("gather_evidence", flow.gather_evidence),
        ("identify_fee", flow.identify_fee),
        ("day_postings", flow.day_postings),
        ("evaluate_rules", flow.evaluate_rules),
        ("find_policy", flow.find_policy),
        ("draft_reply", flow.draft_reply),
        ("guard_output", flow.guard_output),
    ]
    for name, node in pipeline:
        graph.add_node(name, node)
    graph.add_node("finalize", flow.finalize)
    graph.add_edge(START, "load_case")
    for (name, _), (next_name, _) in pairwise(pipeline):
        # Any node may end the flow early (manual review, not a refund): go straight to finalize.
        graph.add_conditional_edges(name, _continue_to(next_name), [next_name, "finalize"])
    graph.add_edge("guard_output", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


def _continue_to(next_node: str) -> Callable[[RunState], str]:
    def route(state: RunState) -> str:
        return "finalize" if state.exit is not None else next_node

    return route


def _required[V](value: V | None) -> V:
    if value is None:
        raise RuntimeError("flow state is missing a value an earlier node must have set")
    return value


def _fee_label(candidate: FeeCandidate) -> str:
    t = candidate.transaction
    name = plain_name(fee_type(t.description)).capitalize()
    return f"{name} of {money(abs(t.amount))} on {day(t.date)} ({t.sub_account_name})"
