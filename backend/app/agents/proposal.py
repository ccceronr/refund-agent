"""Turns the flow's state into the proposal that is saved (R-09, design §3.2, §5.2 finalize).

Pure: no I/O. The recommendation and the tier come from the rules engine only.
"""

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from app.agents.state import RunState
from app.agents.templates import TemplateContext, render_template
from app.rules.model import (
    AutoSignals,
    Recommendation,
    Thresholds,
    Tier,
    TypedAnswer,
)
from app.rules.outcome import decide_tier
from app.tools.schemas import LedgerTransaction

NOT_A_REFUND = "NOT_A_REFUND"  # proposals.reason_code for not_refund exits (design §5.2)
_STATUS_BY_TIER = {
    Tier.AUTO: "auto_resolved",  # if the refund then fails, finalize falls back to "ready"
    Tier.STAFF: "ready",
    Tier.SUPERVISOR: "needs_supervisor",
    Tier.MANUAL: "manual_review",
}


@dataclass(frozen=True)
class ProposalPlan:
    recommendation: Recommendation
    reason_code: str
    tier: Tier
    auto_blockers: tuple[str, ...]
    case_status: str
    category: str
    manual_reason_code: str | None
    fee_transaction_id: int | None
    amount: Decimal | None
    checks: list[dict[str, Any]]
    evidence: dict[str, Any]
    policy_quote: dict[str, Any] | None
    language: str | None
    tone: str | None
    draft_reply: str | None
    draft_source: str | None
    decisions: dict[str, Any]


def build_plan(state: RunState, thresholds: Thresholds) -> ProposalPlan:
    if state.exit is not None and state.exit.kind == "not_refund":
        return _plan_without_evaluation(state, thresholds, NOT_A_REFUND, "not_refund", draft=False)
    if state.exit is not None:
        reason = state.exit.reason.value if state.exit.reason else "AI_UNAVAILABLE"
        return _plan_without_evaluation(state, thresholds, reason, "manual_review", draft=True)
    return _plan_from_evaluation(state, thresholds)


def auto_signals(state: RunState) -> AutoSignals:
    """BR-08: the decisions that count are intent, language, the fee if Jev chose it, and the
    guard's two checks. Tone and the policy passage never count."""
    screening, draft = state.screening, state.draft
    if screening is None or draft is None:
        raise ValueError("auto signals need the screening and the draft")
    answers = [screening.intent_answer, screening.language_answer]
    if draft.guard_decisions is not None:
        guard = draft.guard_decisions
        answers.append(TypedAnswer(guard.source, guard.noul("language").confidence))
        answers.append(TypedAnswer(guard.source, guard.choice("outcome").confidence))
    return AutoSignals(
        typed_answers=tuple(answers),
        fee_choice=state.fee_choice,
        injection_probability=screening.injection_probability,
        draft_source=draft.source,
        guard_passed=draft.source == "writer" and not draft.guard_failures,
    )


def _plan_from_evaluation(state: RunState, thresholds: Thresholds) -> ProposalPlan:
    evaluation, fee, draft = state.evaluation, state.fee, state.draft
    if evaluation is None or fee is None or draft is None:
        raise ValueError("an evaluated case needs its fee and a draft")
    decision = decide_tier(evaluation, auto_signals(state), thresholds)
    manual = evaluation.recommendation is Recommendation.MANUAL
    return ProposalPlan(
        recommendation=evaluation.recommendation,
        reason_code=evaluation.reason_code.value,
        tier=decision.tier,
        auto_blockers=decision.auto_blockers,
        case_status=_STATUS_BY_TIER[decision.tier],
        category="fee_refund",
        manual_reason_code=evaluation.reason_code.value if manual else None,
        fee_transaction_id=fee.transaction.id,
        amount=evaluation.amount,
        checks=[asdict(check) for check in evaluation.checks],
        evidence=_evidence(state, thresholds),
        policy_quote=asdict(state.policy_quote) if state.policy_quote else None,
        language=state.screening.language if state.screening else None,
        tone=state.screening.tone if state.screening else None,
        draft_reply=draft.text,
        draft_source=draft.source,
        decisions=_decisions(state, decision.auto_blockers),
    )


def _plan_without_evaluation(
    state: RunState, thresholds: Thresholds, reason: str, status: str, *, draft: bool
) -> ProposalPlan:
    language = state.screening.language if state.screening else "en"
    reply = _manual_reply(state, thresholds, language) if draft else None
    return ProposalPlan(
        recommendation=Recommendation.MANUAL,
        reason_code=reason,
        tier=Tier.MANUAL,
        auto_blockers=(),
        case_status=status,
        category=_category(state),
        manual_reason_code=reason if status == "manual_review" else None,
        fee_transaction_id=None,
        amount=None,
        checks=[],
        evidence=_evidence(state, thresholds),
        policy_quote=None,
        language=state.screening.language if state.screening else None,
        tone=state.screening.tone if state.screening else None,
        draft_reply=reply,
        draft_source="template" if reply else None,
        decisions=_decisions(state, ()),
    )


def _manual_reply(state: RunState, thresholds: Thresholds, language: str) -> str | None:
    # A neutral start for Luis (no promises), so a manual case never begins from zero.
    if state.case is None:
        return None
    context = TemplateContext(
        state.case.first_name, state.case.credit_union_name, None, thresholds.claim_window_days
    )
    return render_template("MANUAL", "es" if language == "es" else "en", context)


def _category(state: RunState) -> str:
    if state.screening is None:
        return "unknown"
    return {"fee_refund": "fee_refund", "other_banking": "other"}.get(
        state.screening.intent, "unknown"
    )


def _transaction(t: LedgerTransaction, account_numbers: dict[int, str]) -> dict[str, Any]:
    return {
        "id": t.id,
        "sub_account_id": t.sub_account_id,
        "sub_account_name": t.sub_account_name,
        # Full number: only the evidence panel may show it (R-33); the API decides.
        "account_number": account_numbers.get(t.sub_account_id),
        "date": t.date.isoformat(),
        "description": t.description,
        "amount": str(t.amount),
        "balance_after": str(t.balance_after),
        "posting_ref": t.posting_ref,
    }


def _evidence(state: RunState, thresholds: Thresholds) -> dict[str, Any]:
    numbers = {
        sub.id: account.account_number for account in state.accounts for sub in account.sub_accounts
    }
    evidence: dict[str, Any] = {
        "fee": _transaction(state.fee.transaction, numbers) if state.fee else None,
        "day_postings": [_transaction(p, numbers) for p in state.day_postings],
        "refund_history": [_transaction(r, numbers) for r in state.refunds],
        "refunds_limit": thresholds.refund_limit_per_window,
        "standing": [
            {"flag": f.flag, "resolved": f.resolved_at is not None}
            for f in (state.standing.flags if state.standing else [])
        ],
        # BR-09 "Manual cases": an AMBIGUOUS_FEE refund must name one of these.
        "fee_candidates": [_transaction(c.transaction, numbers) for c in state.candidates],
    }
    if state.evaluation is not None:
        evidence["refunds_used"] = state.evaluation.refunds_in_window
    return evidence


def _decisions(state: RunState, auto_blockers: tuple[str, ...]) -> dict[str, Any]:
    screening, draft = state.screening, state.draft
    decisions: dict[str, Any] = {"auto_blockers": list(auto_blockers)}
    if screening is not None:
        decisions["screening"] = {
            "intent": screening.intent,
            "intent_confidence": screening.intent_answer.confidence,
            "injection_probability": screening.injection_probability,
            "language": screening.language,
            "tone": screening.tone,
            "source": screening.intent_answer.source,
        }
    if state.fee_choice is not None:
        decisions["fee_choice"] = asdict(state.fee_choice)
    if draft is not None:
        decisions["guard_failures"] = list(draft.guard_failures)
    return decisions
