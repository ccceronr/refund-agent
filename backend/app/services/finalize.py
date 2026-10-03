"""Saves the run's proposal and case status; on the AUTO tier, refunds and replies (BR-11, BR-12).

Everything happens in one app_rw transaction with the case row locked. A refused
automatic refund keeps the proposal for Luis at the STAFF tier (design §5.2).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import structlog
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.agents.proposal import ProposalPlan
from app.agents.state import FinalOutcome
from app.db.models import Case, Conversation, Message, Proposal
from app.rules.model import Role, Tier
from app.services import audit
from app.services.errors import ApprovalNotAllowed, FeeAlreadyRefunded, NoFeeIdentified
from app.services.refunds import Actor, RefundService

AUTOMATIC_REFUNDS = Actor("S00", Role.SYSTEM)  # seeded staff row "Automatic refunds"

log = structlog.get_logger(__name__)


class Finalizer(Protocol):
    async def finalize(
        self, case_id: int, run_id: uuid.UUID, plan: ProposalPlan
    ) -> FinalOutcome: ...


@dataclass
class DryRunFinalizer:
    """Dry runs (CLI, evals): computes the outcome, writes nothing, never refunds."""

    plan: ProposalPlan | None = None

    async def finalize(self, case_id: int, run_id: uuid.UUID, plan: ProposalPlan) -> FinalOutcome:
        self.plan = plan
        return FinalOutcome(
            plan.case_status,
            plan.recommendation.value,
            plan.reason_code,
            plan.tier.value,
            False,
            None,
        )


class DbFinalizer:
    def __init__(self, engine: AsyncEngine, refunds: RefundService) -> None:
        self._engine = engine
        self._refunds = refunds

    async def finalize(self, case_id: int, run_id: uuid.UUID, plan: ProposalPlan) -> FinalOutcome:
        async with self._engine.begin() as connection:
            await connection.execute(
                select(Case.version).where(Case.conversation_id == case_id).with_for_update()
            )
            tier, status = plan.tier, plan.case_status
            refunded = tier is Tier.AUTO and await self._auto_refund(
                connection, case_id, run_id, plan
            )
            if tier is Tier.AUTO and not refunded:
                tier, status = Tier.STAFF, "ready"
            proposal_id = await _insert_proposal(connection, case_id, run_id, plan, tier)
            if refunded:
                await _send_reply(connection, case_id, plan.draft_reply or "")
            await _update_case(connection, case_id, plan, status, proposal_id)
            await audit.record(
                connection,
                event="proposal_saved",
                actor_id=AUTOMATIC_REFUNDS.staff_id,
                case_id=case_id,
                details={
                    "run_id": str(run_id),
                    "recommendation": plan.recommendation.value,
                    "reason_code": plan.reason_code,
                    "tier": tier.value,
                    "case_status": status,
                },
            )
        return FinalOutcome(
            status, plan.recommendation.value, plan.reason_code, tier.value, refunded, proposal_id
        )

    async def _auto_refund(
        self, connection: AsyncConnection, case_id: int, run_id: uuid.UUID, plan: ProposalPlan
    ) -> bool:
        if plan.fee_transaction_id is None:
            return False
        try:
            async with connection.begin_nested():
                await self._refunds.execute(
                    connection,
                    case_id=case_id,
                    fee_transaction_id=plan.fee_transaction_id,
                    actor=AUTOMATIC_REFUNDS,
                    idempotency_key=f"auto-{run_id}",
                )
        except (FeeAlreadyRefunded, ApprovalNotAllowed, NoFeeIdentified) as error:
            log.warning("auto_refund_refused", case_id=case_id, error=type(error).__name__)
            return False
        return True


async def _insert_proposal(
    connection: AsyncConnection, case_id: int, run_id: uuid.UUID, plan: ProposalPlan, tier: Tier
) -> int:
    inserted = await connection.execute(
        insert(Proposal)
        .values(
            case_id=case_id,
            run_id=run_id,
            recommendation=plan.recommendation.value,
            reason_code=plan.reason_code,
            tier=tier.value,
            fee_transaction_id=plan.fee_transaction_id,
            amount=plan.amount,
            checks={"items": plan.checks},
            evidence=plan.evidence,
            policy_quote=plan.policy_quote,
            language=plan.language,
            tone=plan.tone,
            draft_reply=plan.draft_reply,
            draft_source=plan.draft_source,
            decisions=plan.decisions,
        )
        .returning(Proposal.id)
    )
    proposal_id: int = inserted.scalar_one()
    return proposal_id


async def _send_reply(connection: AsyncConnection, case_id: int, body: str) -> None:
    # BR-12: the reply becomes a message from the automatic flow and the conversation closes.
    await connection.execute(
        insert(Message).values(
            conversation_id=case_id,
            author_id=AUTOMATIC_REFUNDS.staff_id,
            body=body,
            created_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    await connection.execute(
        update(Conversation).where(Conversation.id == case_id).values(status="closed")
    )
    await audit.record(
        connection,
        event="reply_sent",
        actor_id=AUTOMATIC_REFUNDS.staff_id,
        case_id=case_id,
        details={},
    )


async def _update_case(
    connection: AsyncConnection, case_id: int, plan: ProposalPlan, status: str, proposal_id: int
) -> None:
    await connection.execute(
        update(Case)
        .where(Case.conversation_id == case_id)
        .values(
            status=status,
            category=plan.category,
            manual_reason_code=plan.manual_reason_code,
            current_proposal_id=proposal_id,
            updated_at=func.now(),
            version=Case.version + 1,
        )
    )
