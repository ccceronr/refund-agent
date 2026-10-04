"""Staff asks a supervisor to decide a case (ui.md §2.7, design §4.3a).

A case ready for staff moves to `needs_supervisor`, the supervisor's first section. No
money moves and nothing is sent. Who asked is the audit entry (R-35), so the details hold
only codes; the actor comes from the session (OWASP A01). A new run of the flow sets the
case's status again, which ends the request.
"""

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.db.models import AuditLog, Case, Proposal, Staff
from app.services import audit
from app.services.errors import CaseAlreadyDecided, CaseNotFound, InvalidDecision, RunInProgress
from app.services.refunds import Actor

SUPERVISOR_ASKED = "supervisor_asked"
DECIDED = frozenset({"resolved", "auto_resolved"})
WAITING = "needs_supervisor"
SUPERVISORS_DECIDE = "You can decide this case yourself."
ONLY_READY_CASES = "Only a case that's ready for you can go to a supervisor."


async def ask_supervisor(engine: AsyncEngine, case_id: int, actor: Actor) -> str:
    """Returns the case's status. Asking again while it waits changes nothing."""
    async with engine.begin() as connection:
        status = await _lock_status(connection, case_id)
        if status == WAITING:
            return status
        _ensure_askable(status, actor)
        await connection.execute(
            update(Case)
            .where(Case.conversation_id == case_id)
            .values(status=WAITING, updated_at=func.now(), version=Case.version + 1)
        )
        await audit.record(
            connection,
            event=SUPERVISOR_ASKED,
            actor_id=actor.staff_id,
            case_id=case_id,
            details={"from_status": status},
        )
    return WAITING


def asked_by() -> ColumnElement[str | None]:
    """Who sent the case to a supervisor since its current proposal (first name), if anyone.

    Correlated with `Case` and the case's current `Proposal` in the enclosing query; the
    caller shows it only while the case waits for a supervisor.
    """
    return (
        select(Staff.first_name)
        .join(AuditLog, AuditLog.actor_id == Staff.id)
        .where(
            AuditLog.case_id == Case.conversation_id,
            AuditLog.event == SUPERVISOR_ASKED,
            AuditLog.at >= Proposal.created_at,
        )
        .order_by(AuditLog.at.desc())
        .limit(1)
        .scalar_subquery()
    )


async def _lock_status(connection: AsyncConnection, case_id: int) -> str:
    status = await connection.scalar(
        select(Case.status).where(Case.conversation_id == case_id).with_for_update()
    )
    if status is None:
        raise CaseNotFound(f"case {case_id}")
    return status


def _ensure_askable(status: str, actor: Actor) -> None:
    if status in DECIDED:
        raise CaseAlreadyDecided(f"case is {status}")
    if status == "running":
        raise RunInProgress("case is being prepared")
    if actor.role == "supervisor":
        raise InvalidDecision(SUPERVISORS_DECIDE)
    if status != "ready":
        raise InvalidDecision(ONLY_READY_CASES)
