"""Staff decisions on a case: approve, edit or reject (R-14, R-15, R-23; BR-09…BR-12).

One transaction per decision, with the case row locked: the refund (BR-11), the reply,
the status change, the decision record, the feedback eval and the audit entries all
commit together or not at all. The actor always comes from the session (OWASP A01).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

import structlog
from sqlalchemy import Row, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.db.models import Case, Conversation, Decision, FeedbackEval, Message, Proposal
from app.rules.model import ReasonCode, Recommendation
from app.services import audit
from app.services.errors import (
    ApprovalNotAllowed,
    CaseAlreadyDecided,
    CaseNotFound,
    FeeAlreadyRefunded,
    InvalidDecision,
    NoFeeIdentified,
    RunInProgress,
)
from app.services.labels import status_label
from app.services.refunds import Actor, RefundService

Action = Literal["approve", "edit", "reject"]
Outcome = Literal["refund", "no_refund"]
DECIDED = frozenset({"resolved", "auto_resolved"})
APPROVABLE = frozenset({"ready", "needs_supervisor"})

NOTHING_TO_APPROVE = "There's no suggestion to approve for this case. Write a reply instead."
NOTHING_TO_REJECT = "There's no suggestion to reject for this case."
PICK_A_FEE = "Pick one of the fees shown for this case."
NO_FEE_TO_PICK = "A fee can only be picked when it isn't clear which fee the member means."

type Record = Row[*tuple[Any, ...]]  # a result row of any shape
log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class DecisionRequest:
    action: Action
    outcome: Outcome | None = None
    reply_text: str | None = None
    reason: str | None = None
    fee_transaction_id: int | None = None


@dataclass(frozen=True)
class _Plan:
    """What a decision does, worked out before anything is written."""

    outcome: Literal["refund", "no_refund", "none"]
    fee_transaction_id: int | None
    reply: str | None


@dataclass(frozen=True)
class _Decided:
    """Everything recorded about one decision."""

    case: Record
    proposal: Record | None
    request: DecisionRequest
    plan: _Plan
    actor: Actor
    idempotency_key: uuid.UUID
    response: dict[str, Any]


class DecisionService:
    def __init__(self, engine: AsyncEngine, refunds: RefundService) -> None:
        self._engine = engine
        self._refunds = refunds

    async def decide(
        self, case_id: int, request: DecisionRequest, actor: Actor, idempotency_key: uuid.UUID
    ) -> dict[str, Any]:
        try:
            async with self._engine.begin() as connection:
                return await self._decide(connection, case_id, request, actor, idempotency_key)
        except (ApprovalNotAllowed, FeeAlreadyRefunded) as refused:
            # The decision rolled back; the refused attempt is still on record (OWASP A09).
            await self._record_refusal(case_id, actor, type(refused).__name__)
            raise

    async def _decide(
        self,
        connection: AsyncConnection,
        case_id: int,
        request: DecisionRequest,
        actor: Actor,
        idempotency_key: uuid.UUID,
    ) -> dict[str, Any]:
        case = await _lock_case(connection, case_id)
        previous = await _previous_response(connection, case_id, idempotency_key)
        if previous is not None:
            return previous  # R-15: the same key gets the original result
        _ensure_open(case)
        proposal = await _current_proposal(connection, case.current_proposal_id)
        plan = _plan(request, case, proposal)
        refunded = None
        if plan.fee_transaction_id is not None:
            refunded = await self._refunds.execute(
                connection,
                case_id=case_id,
                fee_transaction_id=plan.fee_transaction_id,
                actor=actor,
                idempotency_key=str(idempotency_key),
            )
        status = await _apply(connection, case, plan, actor)
        response = {
            "case_id": case_id,
            "status": status,
            "status_label": status_label(status),
            "action": request.action,
            "outcome": plan.outcome,
            "refunded": refunded is not None,
            "amount": str(refunded.amount) if refunded else None,
        }
        await _record(
            connection, _Decided(case, proposal, request, plan, actor, idempotency_key, response)
        )
        return response

    async def _record_refusal(self, case_id: int, actor: Actor, refusal: str) -> None:
        async with self._engine.begin() as connection:
            await audit.record(
                connection,
                event="decision_refused",
                actor_id=actor.staff_id,
                case_id=case_id,
                details={"refusal": refusal},
            )


async def _lock_case(connection: AsyncConnection, case_id: int) -> Record:
    # design §4.3: row lock on the case; concurrent decisions on it wait here.
    case = (
        await connection.execute(
            select(
                Case.conversation_id,
                Case.status,
                Case.manual_reason_code,
                Case.current_proposal_id,
                Case.version,
            )
            .where(Case.conversation_id == case_id)
            .with_for_update()
        )
    ).first()
    if case is None:
        raise CaseNotFound(f"case {case_id}")
    return case


async def _previous_response(
    connection: AsyncConnection, case_id: int, idempotency_key: uuid.UUID
) -> dict[str, Any] | None:
    response: dict[str, Any] | None = await connection.scalar(
        select(Decision.response).where(
            Decision.case_id == case_id, Decision.idempotency_key == idempotency_key
        )
    )
    return response


def _ensure_open(case: Record) -> None:
    if case.status in DECIDED:
        raise CaseAlreadyDecided(f"case {case.conversation_id} is {case.status}")
    if case.status == "running":
        raise RunInProgress(f"case {case.conversation_id} is being prepared")


async def _current_proposal(connection: AsyncConnection, proposal_id: int | None) -> Record | None:
    if proposal_id is None:
        return None
    query = select(
        Proposal.id,
        Proposal.recommendation,
        Proposal.reason_code,
        Proposal.tier,
        Proposal.fee_transaction_id,
        Proposal.draft_reply,
        Proposal.evidence,
    ).where(Proposal.id == proposal_id)
    return (await connection.execute(query)).first()


def _plan(request: DecisionRequest, case: Record, proposal: Record | None) -> _Plan:
    if request.action == "approve":
        return _approve_plan(request, case, proposal)
    if request.action == "edit":
        return _edit_plan(request, case, proposal)
    if proposal is None:
        raise InvalidDecision(NOTHING_TO_REJECT)
    if request.fee_transaction_id is not None:
        raise InvalidDecision(NO_FEE_TO_PICK)
    return _Plan("none", None, None)


def _approve_plan(request: DecisionRequest, case: Record, proposal: Record | None) -> _Plan:
    """Executes the current proposal as it is (design §4.3)."""
    if request.fee_transaction_id is not None:
        raise InvalidDecision(NO_FEE_TO_PICK)
    if proposal is None or case.status not in APPROVABLE:
        raise InvalidDecision(NOTHING_TO_APPROVE)
    if proposal.recommendation == Recommendation.MANUAL or not proposal.draft_reply:
        raise InvalidDecision(NOTHING_TO_APPROVE)
    if proposal.recommendation == Recommendation.NO_REFUND:
        return _Plan("no_refund", None, proposal.draft_reply)
    if proposal.fee_transaction_id is None:  # a REFUND always names its fee; never guess one
        raise NoFeeIdentified(f"case {case.conversation_id}")
    return _Plan("refund", proposal.fee_transaction_id, proposal.draft_reply)


def _edit_plan(request: DecisionRequest, case: Record, proposal: Record | None) -> _Plan:
    if request.outcome is None or request.reply_text is None:
        raise InvalidDecision("Choose what to do and write the reply.")
    if request.outcome == "no_refund":
        if request.fee_transaction_id is not None:
            raise InvalidDecision(NO_FEE_TO_PICK)
        return _Plan("no_refund", None, request.reply_text)
    return _Plan("refund", _fee_to_refund(request, case, proposal), request.reply_text)


def _fee_to_refund(request: DecisionRequest, case: Record, proposal: Record | None) -> int:
    """BR-09 "Manual cases": only an AMBIGUOUS_FEE case lets Luis pick the fee."""
    if case.manual_reason_code == ReasonCode.AMBIGUOUS_FEE:
        candidates = ((proposal.evidence or {}) if proposal else {}).get("fee_candidates", [])
        if request.fee_transaction_id not in {fee["id"] for fee in candidates}:
            raise InvalidDecision(PICK_A_FEE)
        return request.fee_transaction_id  # type: ignore[return-value]  # checked just above
    if request.fee_transaction_id is not None:
        raise InvalidDecision(NO_FEE_TO_PICK)
    if proposal is None or proposal.fee_transaction_id is None:
        raise NoFeeIdentified(f"case {case.conversation_id}")
    fee_id: int = proposal.fee_transaction_id
    return fee_id


async def _apply(connection: AsyncConnection, case: Record, plan: _Plan, actor: Actor) -> str:
    """BR-12: a reply is sent and the case resolved; a rejection goes back to Luis."""
    if plan.reply is None:
        await _update_case(connection, case, "manual_review", ReasonCode.REJECTED_BY_STAFF.value)
        return "manual_review"
    await connection.execute(
        insert(Message).values(
            conversation_id=case.conversation_id,
            author_id=actor.staff_id,
            body=plan.reply,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    await connection.execute(
        update(Conversation).where(Conversation.id == case.conversation_id).values(status="closed")
    )
    await _update_case(connection, case, "resolved", case.manual_reason_code)
    return "resolved"


async def _update_case(
    connection: AsyncConnection, case: Record, status: str, manual_reason_code: str | None
) -> None:
    updated = await connection.execute(
        update(Case)
        .where(Case.conversation_id == case.conversation_id, Case.version == case.version)
        .values(
            status=status,
            manual_reason_code=manual_reason_code,
            updated_at=func.now(),
            version=Case.version + 1,
        )
    )
    if updated.rowcount != 1:  # cannot happen under the row lock; never continue if it does
        raise RuntimeError(f"case {case.conversation_id} changed during the decision")


async def _record(connection: AsyncConnection, decided: _Decided) -> None:
    case, proposal, request, plan = decided.case, decided.proposal, decided.request, decided.plan
    await connection.execute(
        insert(Decision).values(
            case_id=case.conversation_id,
            proposal_id=proposal.id if proposal else None,
            actor_id=decided.actor.staff_id,
            action=request.action,
            outcome=plan.outcome,
            reply_text=plan.reply,
            reason=request.reason,
            idempotency_key=decided.idempotency_key,
            response=decided.response,
        )
    )
    if proposal is not None and _staff_disagreed(request, plan, proposal):
        await _record_feedback_eval(connection, decided, proposal)
    await audit.record(
        connection,
        event="decision_recorded",
        actor_id=decided.actor.staff_id,
        case_id=case.conversation_id,
        details={
            "action": request.action,
            "outcome": plan.outcome,
            "proposal_id": proposal.id if proposal else None,
            "status": decided.response["status"],
            "idempotency_key": str(decided.idempotency_key),
        },
    )


def _staff_disagreed(request: DecisionRequest, plan: _Plan, proposal: Record) -> bool:
    """R-23: a rejection, or an edit that changed the outcome or the reply."""
    if request.action == "reject":
        return True
    if request.action != "edit":
        return False
    proposed = "refund" if proposal.recommendation == Recommendation.REFUND else "no_refund"
    return plan.outcome != proposed or plan.reply != proposal.draft_reply


async def _record_feedback_eval(
    connection: AsyncConnection, decided: _Decided, proposal: Record
) -> None:
    case, request, plan = decided.case, decided.request, decided.plan
    # seed-and-evals §3.1 format; `expected` is what staff decided. Exported for review
    # before it joins the eval set, never trusted automatically (LLM04).
    expected = {"refund": "REFUND", "no_refund": "NO_REFUND"}.get(plan.outcome)
    payload = {
        "conversation_id": case.conversation_id,
        "message_override": None,
        "expected": {"recommendation": expected} if expected else {},
        "proposal": {
            "recommendation": proposal.recommendation,
            "reason_code": proposal.reason_code,
            "tier": proposal.tier,
        },
        "staff": {
            "action": request.action,
            "outcome": plan.outcome,
            "reply_changed": request.action == "edit" and plan.reply != proposal.draft_reply,
            "reason": request.reason,
        },
    }
    await connection.execute(
        insert(FeedbackEval).values(case_id=case.conversation_id, payload=payload)
    )
