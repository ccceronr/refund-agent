"""Agent runs and steps, persisted as they happen so they survive a restart (R-30, R-34)."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

import structlog
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agents.steps import StepRecord
from app.db.models import AgentRun, AgentStep, Case
from app.rules.model import ReasonCode
from app.services import audit
from app.services.errors import CaseAlreadyDecided, CaseNotFound, RunInProgress

DECIDED_STATUSES = frozenset({"resolved", "auto_resolved"})

log = structlog.get_logger(__name__)


class RunStore(Protocol):
    async def start(self, case_id: int, run_id: uuid.UUID, request_id: str | None) -> None: ...
    async def add_step(self, run_id: uuid.UUID, record: StepRecord) -> None: ...
    async def finish(
        self,
        run_id: uuid.UUID,
        *,
        status: str,
        error_code: str | None,
        cost: Decimal,
        latency_ms: int,
    ) -> None: ...


class DbRunStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def start(self, case_id: int, run_id: uuid.UUID, request_id: str | None) -> None:
        """One run per case at a time (design §4: 409 while running or once resolved)."""
        async with self._engine.begin() as connection:
            status = await connection.scalar(
                select(Case.status).where(Case.conversation_id == case_id).with_for_update()
            )
            if status is None:
                raise CaseNotFound(f"case {case_id}")
            if status == "running":
                raise RunInProgress(f"case {case_id} is already being prepared")
            if status in DECIDED_STATUSES:
                raise CaseAlreadyDecided(f"case {case_id} is {status}")
            await connection.execute(
                update(Case)
                .where(Case.conversation_id == case_id)
                .values(status="running", updated_at=func.now(), version=Case.version + 1)
            )
            await connection.execute(
                insert(AgentRun).values(
                    id=run_id, case_id=case_id, status="running", request_id=request_id
                )
            )

    async def add_step(self, run_id: uuid.UUID, record: StepRecord) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                insert(AgentStep).values(
                    run_id=run_id,
                    ordinal=record.ordinal,
                    name=record.name,
                    label=record.label,
                    kind=record.kind,
                    provider=record.provider,
                    model=record.model,
                    status=record.status,
                    latency_ms=record.latency_ms,
                    input_tokens=record.input_tokens,
                    output_tokens=record.output_tokens,
                    cost_usd=record.cost_usd,
                    used_fallback=record.used_fallback,
                    error_code=record.error_code,
                    output=record.output,
                    started_at=record.started_at,
                )
            )

    async def finish(
        self,
        run_id: uuid.UUID,
        *,
        status: str,
        error_code: str | None,
        cost: Decimal,
        latency_ms: int,
    ) -> None:
        async with self._engine.begin() as connection:
            await connection.execute(
                update(AgentRun)
                .where(AgentRun.id == run_id)
                .values(
                    status=status,
                    error_code=error_code,
                    total_cost_usd=cost,
                    total_latency_ms=latency_ms,
                    finished_at=func.now(),
                )
            )


@dataclass
class MemoryRunStore:
    """Dry runs (CLI, evals): nothing is written to the database."""

    steps: list[StepRecord] = field(default_factory=list)
    status: str | None = None
    error_code: str | None = None

    async def start(self, case_id: int, run_id: uuid.UUID, request_id: str | None) -> None:
        return None

    async def add_step(self, run_id: uuid.UUID, record: StepRecord) -> None:
        self.steps.append(record)

    async def finish(
        self,
        run_id: uuid.UUID,
        *,
        status: str,
        error_code: str | None,
        cost: Decimal,
        latency_ms: int,
    ) -> None:
        self.status, self.error_code = status, error_code


async def recover_interrupted_runs(engine: AsyncEngine) -> int:
    """At startup: a run left `running` died with the process (design §5.2) → TIMEOUT."""
    async with engine.begin() as connection:
        interrupted = (
            (
                await connection.execute(
                    update(AgentRun)
                    .where(AgentRun.status == "running")
                    .values(
                        status="failed",
                        error_code=ReasonCode.TIMEOUT.value,
                        finished_at=datetime.now(UTC),
                    )
                    .returning(AgentRun.case_id)
                )
            )
            .scalars()
            .all()
        )
        for case_id in set(interrupted):
            await connection.execute(
                update(Case)
                .where(Case.conversation_id == case_id, Case.status == "running")
                .values(
                    status="manual_review",
                    manual_reason_code=ReasonCode.TIMEOUT.value,
                    updated_at=func.now(),
                    version=Case.version + 1,
                )
            )
            await audit.record(
                connection,
                event="run_interrupted",
                actor_id=None,
                case_id=case_id,
                details={"reason_code": ReasonCode.TIMEOUT.value},
            )
    if interrupted:
        log.warning("runs_recovered", count=len(interrupted))
    return len(interrupted)
