"""The agent flow end to end with the models faked (tasks P5; R-04…R-13, R-16, R-20, R-30).

Tools, rules, templates, guard and persistence are real; only Jev/Haiku and the writer
are scripted, so no test calls a model.
"""

import asyncio
import io
import json
import uuid
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import text

from app.agents.decider import Decisions, State
from app.agents.errors import ModelUnavailable
from app.agents.questions import ChoiceAnswer, NoulAnswer, Question
from app.agents.run_case import CaseRunner, RunResult, SlowDecider
from app.agents.steps import QueueSink
from app.agents.writer import ReplyFacts, WrittenReply
from app.core.config import Settings
from app.core.pricing import TokenUsage
from app.db.engines import create_ro_engine, create_rw_engine
from app.rules.texts import money
from app.services.errors import RunInProgress
from app.services.finalize import DryRunFinalizer
from app.services.runs import recover_interrupted_runs

DENIAL_WORDS = ("can't", "cannot", "no podemos")


class ScriptedDecider:
    """Answers like Jev would, from a script. Records which question sets it was asked."""

    def __init__(self, *, intent: str = "fee_refund", intent_confidence: float = 0.99, injection: float = 0.01,
                 language: str = "en", fee: str = "fee_1", fee_confidence: float = 0.97,
                 source: str = "jev", down: bool = False) -> None:  # fmt: skip
        self.script = {"intent": intent, "intent_confidence": intent_confidence, "injection": injection, "language": language, "fee": fee, "fee_confidence": fee_confidence}  # fmt: skip
        self.source = source
        self.down = down
        self.asked: list[frozenset[str]] = []
        self.states: list[State] = []

    async def decide(self, state: State, questions: Mapping[str, Question]) -> Decisions:
        self.asked.append(frozenset(questions))
        self.states.append(state)
        if self.down:
            raise ModelUnavailable("jev", "http_529")
        s = self.script
        if "intent" in questions:
            answers: dict[str, Any] = {
                "intent": ChoiceAnswer(choice=s["intent"], confidence=s["intent_confidence"]),
                "injection": NoulAnswer(noul=s["injection"]),
                "language": ChoiceAnswer(choice=s["language"], confidence=0.99),
                "tone": ChoiceAnswer(choice="neutral", confidence=0.7),
            }
        elif "fee" in questions:
            answers = {"fee": ChoiceAnswer(choice=s["fee"], confidence=s["fee_confidence"])}
        elif "passage" in questions:
            answers = {"passage": ChoiceAnswer(choice="p1", confidence=0.9)}
        else:  # the guard's language and outcome checks
            denied = any(word in str(state).lower() for word in DENIAL_WORDS)
            outcome = "refund_denied" if denied else "refund_confirmed"
            answers = {
                "language": NoulAnswer(noul=0.99),
                "outcome": ChoiceAnswer(choice=outcome, confidence=0.98),
            }
        return Decisions(
            answers,
            self.source,
            "jev-1.13.0",
            TokenUsage(input_tokens=100),
            Decimal("0.0000042"),
            3,
        )  # type: ignore[arg-type]


class FakeWriter:
    def __init__(self, *, fail: bool = False, text: str | None = None) -> None:
        self.fail, self.text, self.calls = fail, text, 0

    async def write(self, facts: ReplyFacts) -> WrittenReply:
        self.calls += 1
        if self.fail:
            raise ModelUnavailable("anthropic", "http_529")
        amount, signature = money(facts.amount), f"{facts.credit_union_name} Member Support"
        if facts.outcome == "REFUND":
            body = f"Hi {facts.first_name},\n\nWe've refunded the {amount} {facts.fee_name}. The money is back in your account today.\n\n{signature}"
        else:
            body = f"Hi {facts.first_name},\n\nWe can't refund the {amount} {facts.fee_name}. {facts.reason} Is there anything else we can help with?\n\n{signature}"
        usage = TokenUsage(input_tokens=50, output_tokens=40, cache_read_tokens=600)
        return WrittenReply(self.text or body, "claude-sonnet-5-5", usage, Decimal("0.0005"), 12)


Run = Callable[..., Any]


@pytest.fixture
def run(seeded_db: dict[str, str], make_settings: Callable[..., Settings]) -> Run:
    async def _run(case_id: int, *, decider: Any = None, writer: Any = None, dry_run: bool = True,
                   events: QueueSink | None = None, **settings: Any) -> tuple[CaseRunner, RunResult]:  # fmt: skip
        config = make_settings(**settings)
        ro, rw = create_ro_engine(config), None if dry_run else create_rw_engine(config)
        runner = CaseRunner(settings=config, ro_engine=ro, rw_engine=rw, decider=decider or ScriptedDecider(),
                            writer=writer or FakeWriter(), events=events)  # fmt: skip
        try:
            return runner, await runner.run(case_id)
        finally:
            await ro.dispose()
            if rw is not None:
                await rw.dispose()

    return _run


def plan_of(runner: CaseRunner):
    assert isinstance(runner.finalizer, DryRunFinalizer)
    return runner.finalizer.plan


def step_names(runner: CaseRunner) -> list[str]:
    return [s.name for s in runner.store.steps]  # type: ignore[attr-defined]


# --- Routing ---------------------------------------------------------------------------


async def test_suspected_injection_stops_before_reading_any_account(run: Run) -> None:
    runner, _ = await run(5022, decider=ScriptedDecider(injection=0.9))

    plan = plan_of(runner)
    assert (plan.recommendation.value, plan.reason_code, plan.case_status) == (
        "MANUAL",
        "INJECTION_SUSPECTED",
        "manual_review",
    )
    assert step_names(runner) == ["load_case", "screen", "finalize"]
    assert plan.draft_source == "template"  # the neutral manual reply, no promises


async def test_screening_reads_the_subject_and_the_member_messages_only(run: Run) -> None:
    # design §6.1/§8: the subject Luis also sees, then the member's messages; no names or IDs.
    decider = ScriptedDecider()

    await run(5012, decider=decider)

    assert decider.states[0] == (
        "Subject: Overdraft fee\nMember: My paycheck came the same day. Can you refund this?"
    )


async def test_another_kind_of_request_is_not_a_refund(run: Run) -> None:
    runner, _ = await run(5011, decider=ScriptedDecider(intent="other_banking"))

    plan = plan_of(runner)
    assert (plan.reason_code, plan.case_status, plan.category, plan.draft_reply) == (
        "NOT_A_REFUND",
        "not_refund",
        "other",
        None,
    )


@pytest.mark.parametrize(
    ("intent", "confidence"), [("unclear", 0.99), ("fee_refund", 0.6), ("other_banking", 0.6)]
)
async def test_an_unclear_or_unsure_intent_goes_to_manual_review(
    run: Run, intent: str, confidence: float
) -> None:
    runner, _ = await run(
        5030, decider=ScriptedDecider(intent=intent, intent_confidence=confidence)
    )

    assert plan_of(runner).reason_code == "INTENT_UNCLEAR"


async def test_no_fee_in_the_lookback_is_no_fee_found(run: Run) -> None:
    runner, _ = await run(5027)

    assert plan_of(runner).reason_code == "NO_FEE_FOUND"


async def test_a_single_fee_is_identified_without_asking_a_model(run: Run) -> None:
    decider = ScriptedDecider()
    runner, _ = await run(5012, decider=decider)

    plan = plan_of(runner)
    assert not any("fee" in asked for asked in decider.asked)
    assert (plan.fee_transaction_id, plan.amount, plan.recommendation.value) == (
        88002,
        Decimal("35.00"),
        "REFUND",
    )
    assert (plan.tier.value, plan.case_status, plan.auto_blockers) == (
        "STAFF",
        "ready",
        ("last_refund",),
    )


async def test_with_several_fees_jev_picks_the_one_the_member_means(run: Run) -> None:
    runner, result = await run(5024, decider=ScriptedDecider(fee="fee_2"))

    assert result.final_state.fee is not None
    assert result.final_state.fee.transaction.date.isoformat() == "2026-09-21"
    assert plan_of(runner).recommendation.value == "REFUND"


@pytest.mark.parametrize(("fee", "confidence"), [("unclear", 0.99), ("fee_1", 0.7)])
async def test_an_unclear_fee_choice_is_ambiguous_and_keeps_the_candidates(
    run: Run, fee: str, confidence: float
) -> None:
    runner, _ = await run(5023, decider=ScriptedDecider(fee=fee, fee_confidence=confidence))

    plan = plan_of(runner)
    assert plan.reason_code == "AMBIGUOUS_FEE"
    assert len(plan.evidence["fee_candidates"]) == 2  # BR-09: Luis may pick one of these


# --- Tiers and drafts --------------------------------------------------------------------


async def test_a_clean_case_reaches_the_automatic_tier(run: Run) -> None:
    runner, _ = await run(5013)

    plan = plan_of(runner)
    assert (plan.tier.value, plan.case_status, plan.draft_source) == (
        "AUTO",
        "auto_resolved",
        "writer",
    )


async def test_a_writer_failure_uses_the_template_and_blocks_auto(run: Run) -> None:
    runner, _ = await run(5013, writer=FakeWriter(fail=True))

    plan = plan_of(runner)
    assert plan.draft_source == "template"
    assert "Daniel" in (plan.draft_reply or "")
    assert (plan.tier.value, plan.auto_blockers) == ("STAFF", ("draft",))


async def test_a_draft_that_fails_the_guard_is_replaced_by_the_template(run: Run) -> None:
    runner, _ = await run(5013, writer=FakeWriter(text="Hi Daniel, we refunded $500.00 today."))

    plan = plan_of(runner)
    assert plan.draft_source == "template"
    assert plan.decisions["guard_failures"] == ["amount"]
    assert "$500.00" not in (plan.draft_reply or "")


async def test_fallback_answers_never_reach_the_automatic_tier(run: Run) -> None:
    runner, _ = await run(5013, decider=ScriptedDecider(source="fallback"))

    assert plan_of(runner).auto_blockers == ("fallback_used",)


async def test_a_no_refund_case_explains_the_reason_through_the_writer(run: Run) -> None:
    runner, _ = await run(5015)

    plan = plan_of(runner)
    assert (plan.reason_code, plan.draft_source) == ("LIMIT_REACHED", "writer")
    assert "Olivia has already used all 3 refunds" in (plan.draft_reply or "")


async def test_the_policy_quote_is_a_verbatim_seeded_passage(run: Run) -> None:
    runner, _ = await run(5015)

    quote = plan_of(runner).policy_quote
    assert quote is not None
    assert quote["document_title"] == "Fee Refund Policy"
    assert quote["text"].startswith("Members in good standing may receive up to 3 fee refunds")


# --- Failures ------------------------------------------------------------------------------


async def test_when_both_models_are_down_the_case_goes_to_manual_review(run: Run) -> None:
    runner, _ = await run(5012, decider=ScriptedDecider(down=True))

    assert plan_of(runner).reason_code == "AI_UNAVAILABLE"
    assert runner.store.status == "failed"  # type: ignore[attr-defined]


class BrokenDecider(ScriptedDecider):
    """A bug, not an outage: the error message carries member data on purpose."""

    member_data = "Ana Lopez ••4210"

    async def decide(self, state: State, questions: Mapping[str, Question]) -> Decisions:
        raise KeyError(self.member_data)


async def test_an_unexpected_error_goes_to_manual_review_with_its_own_code(
    run: Run, log_output: io.StringIO
) -> None:
    runner, _ = await run(5012, decider=BrokenDecider())

    assert plan_of(runner).case_status == "manual_review"
    assert (runner.store.status, runner.store.error_code) == ("failed", "UNEXPECTED_ERROR")  # type: ignore[attr-defined]
    screen = next(s for s in runner.store.steps if s.name == "screen")  # type: ignore[attr-defined]
    assert (screen.status, screen.error_code) == ("failed", "UNEXPECTED_ERROR")
    [crash] = [
        json.loads(line) for line in log_output.getvalue().splitlines() if "run_crashed" in line
    ]
    assert (crash["level"], crash["error_type"]) == ("error", "KeyError")
    assert crash["traceback"]
    assert "Ana" not in log_output.getvalue()


async def test_a_run_over_the_time_limit_goes_to_manual_review(run: Run) -> None:
    runner, _ = await run(
        5012, decider=SlowDecider(ScriptedDecider(), 1.0), run_timeout_seconds=0.2
    )

    assert plan_of(runner).reason_code == "TIMEOUT"
    assert (runner.store.status, runner.store.error_code) == ("failed", "TIMEOUT")  # type: ignore[attr-defined]


async def test_each_step_is_streamed_as_it_runs(run: Run) -> None:
    events = QueueSink()
    await run(5012, events=events)

    received = []
    while not events.queue.empty():
        received.append(events.queue.get_nowait())
    steps = [(data["label"], data["status"]) for event, data in received if event == "step"]
    assert steps[:2] == [
        ("Opening the conversation", "running"),
        ("Opening the conversation", "done"),
    ]
    assert ("Writing the reply", "done") in steps
    assert received[-1] == ("completed", {"case_id": 5012, "status": "ready"})


# --- Real runs: persistence, refund, recovery ------------------------------------------


async def query(make_settings: Callable[..., Settings], sql: str) -> list[tuple[Any, ...]]:
    engine = create_rw_engine(make_settings())
    try:
        async with engine.connect() as connection:
            return [tuple(r) for r in await connection.execute(text(sql))]
    finally:
        await engine.dispose()


async def test_the_automatic_tier_refunds_replies_and_closes_the_case(
    fresh_db, run: Run, make_settings
) -> None:
    _, result = await run(5013, dry_run=False)

    assert result.outcome.refunded
    assert await query(make_settings, "SELECT status FROM cases WHERE conversation_id = 5013") == [
        ("auto_resolved",)
    ]
    assert await query(make_settings, "SELECT status FROM conversations WHERE id = 5013") == [
        ("closed",)
    ]
    assert await query(
        make_settings,
        "SELECT author_id FROM messages WHERE conversation_id = 5013 ORDER BY id DESC LIMIT 1",
    ) == [("S00",)]
    assert await query(
        make_settings, "SELECT amount, actor_id FROM refund_actions WHERE case_id = 5013"
    ) == [(Decimal("35.00"), "S00")]
    assert await query(make_settings, "SELECT status FROM agent_runs") == [("completed",)]
    labels = await query(make_settings, "SELECT label FROM agent_steps ORDER BY ordinal")
    assert labels[0] == ("Opening the conversation",)
    assert labels[-1] == ("Refunded automatically",)


async def test_a_staff_case_is_saved_ready_for_luis_without_a_refund(
    fresh_db, run: Run, make_settings
) -> None:
    await run(5012, dry_run=False)

    assert await query(
        make_settings,
        "SELECT status, current_proposal_id IS NOT NULL FROM cases WHERE conversation_id = 5012",
    ) == [("ready", True)]
    assert await query(
        make_settings, "SELECT tier, recommendation FROM proposals WHERE case_id = 5012"
    ) == [("STAFF", "REFUND")]
    assert await query(make_settings, "SELECT count(*) FROM refund_actions") == [(0,)]


async def test_a_case_that_is_already_running_cannot_be_run_again(
    fresh_db, run: Run, make_settings
) -> None:
    engine = create_rw_engine(make_settings())
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE cases SET status = 'running' WHERE conversation_id = 5012")
        )
    await engine.dispose()

    with pytest.raises(RunInProgress):
        await run(5012, dry_run=False)


async def test_runs_interrupted_by_a_crash_become_timeouts_at_startup(
    fresh_db, make_settings
) -> None:
    engine = create_rw_engine(make_settings())
    async with engine.begin() as connection:
        await connection.execute(
            text("UPDATE cases SET status = 'running' WHERE conversation_id = 5012")
        )
        await connection.execute(
            text("INSERT INTO agent_runs (id, case_id, status) VALUES (:id, 5012, 'running')"),
            {"id": uuid.uuid4()},
        )

    recovered = await recover_interrupted_runs(engine)
    await engine.dispose()

    assert recovered == 1
    assert await query(make_settings, "SELECT status, error_code FROM agent_runs") == [
        ("failed", "TIMEOUT")
    ]
    assert await query(
        make_settings, "SELECT status, manual_reason_code FROM cases WHERE conversation_id = 5012"
    ) == [("manual_review", "TIMEOUT")]


def test_the_runner_never_writes_in_a_dry_run(run: Run) -> None:
    runner, _ = asyncio.run(run(5013))

    assert isinstance(runner.finalizer, DryRunFinalizer)
