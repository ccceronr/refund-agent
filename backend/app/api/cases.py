"""The queue, the case page, running the flow and staff decisions (design §4; R-01…R-03,
R-14…R-17). HTTP only: validation, status codes and serialization; the work is in services.
"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, Header, Path, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, format_sse_event
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.agents.batch import NewCase, prepare_cases
from app.agents.run_case import RunResult
from app.agents.steps import QueueSink
from app.api.dependencies import (
    AppSettings,
    CurrentStaff,
    Decisions,
    RunnerFactory,
    RwEngine,
)
from app.db.models import CASE_STATUSES
from app.rules.model import Thresholds
from app.services.auth import StaffMember
from app.services.case_views import case_detail, done_since, list_cases
from app.services.decisions import DecisionRequest
from app.services.errors import PreparationInProgress
from app.services.escalations import ask_supervisor
from app.services.labels import status_label
from app.services.refunds import Actor
from app.services.view_models import CaseDetail, CaseListItem

MAX_ID = 2_147_483_647  # Postgres integer
CaseId = Annotated[int, Path(gt=0, le=MAX_ID)]
CaseStatus = Literal[CASE_STATUSES]  # type: ignore[valid-type]  # the tuple of allowed values
ReplyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
EVENT_STREAM = "text/event-stream"
RUN_ENDED_WITHOUT_RESULT = "Preparing this case failed. Try again, or handle it yourself."
BATCH_ENDED_EARLY = "Preparing the new messages stopped early. Try again in a moment."
FINAL_BATCH_EVENTS = frozenset({"done", "failed"})

log = structlog.get_logger(__name__)


class DecisionBody(BaseModel):
    """design §4.3. Unknown fields (an actor, an amount…) are refused: 422."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["approve", "edit", "reject"]
    outcome: Literal["refund", "no_refund"] | None = None
    reply_text: ReplyText | None = None
    reason: Reason | None = None
    fee_transaction_id: Annotated[int, Field(gt=0, le=MAX_ID)] | None = None


class EscalationResponse(BaseModel):
    case_id: int
    status: str
    status_label: str


class DecisionResponse(BaseModel):
    case_id: int
    status: str
    status_label: str
    action: str
    outcome: str
    refunded: bool
    amount: str | None


async def list_queue(
    engine: RwEngine,
    settings: AppSettings,
    status: Annotated[CaseStatus | None, Query()] = None,
) -> list[CaseListItem]:
    since = done_since(datetime.now(UTC), settings.queue_done_window_hours)
    async with engine.connect() as connection:
        return await list_cases(connection, status=status, done_since=since)


async def get_case(
    case_id: CaseId, staff: CurrentStaff, engine: RwEngine, settings: AppSettings
) -> CaseDetail:
    async with engine.connect() as connection:
        return await case_detail(connection, case_id, staff, Thresholds.from_settings(settings))


async def run_case(
    case_id: CaseId,
    request: Request,
    staff: CurrentStaff,
    runners: RunnerFactory,
    engine: RwEngine,
    settings: AppSettings,
) -> Response:
    """design §4.4: SSE when the client asks for text/event-stream, otherwise JSON."""
    events = QueueSink()
    runner = runners(events)
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    run_id = await runner.claim(case_id, request_id)  # 404 / 409 / 429 before streaming
    # The run goes on if the browser disconnects, so the case never stays "running".
    run = asyncio.create_task(runner.execute(case_id, run_id))
    _keep_until_done(request, run)

    async def detail() -> dict[str, Any]:
        view = await get_case(case_id, staff, engine, settings)
        return view.model_dump(mode="json", by_alias=True)

    if EVENT_STREAM in request.headers.get("accept", ""):
        return EventSourceResponse(_sse(events, run, detail))
    await asyncio.shield(run)
    return JSONResponse(await detail())


async def prepare_new(
    request: Request, engine: RwEngine, settings: AppSettings, runners: RunnerFactory
) -> EventSourceResponse:
    """R-03: prepares every new case on the server, one after another, with SSE progress."""
    lock: asyncio.Lock = request.app.state.batch_lock
    if lock.locked():
        raise PreparationInProgress
    await lock.acquire()  # never waits: just checked, and no await in between
    try:
        since = done_since(datetime.now(UTC), settings.queue_done_window_hours)
        async with engine.connect() as connection:
            queue = await list_cases(connection, status="new", done_since=since)
    except BaseException:
        lock.release()
        raise
    events = QueueSink()
    cases = [NewCase(item.id, item.member_name) for item in queue]
    batch = asyncio.create_task(_release_when_done(lock, prepare_cases(cases, runners, events)))
    _keep_until_done(request, batch)
    return EventSourceResponse(_batch_sse(events, batch))


async def decide(
    case_id: CaseId,
    body: DecisionBody,
    idempotency_key: Annotated[uuid.UUID, Header(alias="Idempotency-Key")],
    staff: CurrentStaff,
    decisions: Decisions,
) -> DecisionResponse:
    # The actor is the signed-in staff member, never anything in the request (OWASP A01).
    response = await decisions.decide(
        case_id,
        DecisionRequest(**body.model_dump()),
        _actor(staff),
        idempotency_key,
    )
    return DecisionResponse(**response)


async def escalate(case_id: CaseId, staff: CurrentStaff, engine: RwEngine) -> EscalationResponse:
    """design §4.3a: staff sends a ready case to a supervisor. Safe to send twice."""
    status = await ask_supervisor(engine, case_id, _actor(staff))
    return EscalationResponse(case_id=case_id, status=status, status_label=status_label(status))


router = APIRouter(prefix="/cases")
router.add_api_route("", list_queue, methods=["GET"])
router.add_api_route("/prepare-new", prepare_new, methods=["POST"])
router.add_api_route("/{case_id}", get_case, methods=["GET"])
router.add_api_route("/{case_id}/run", run_case, methods=["POST"])
router.add_api_route("/{case_id}/decision", decide, methods=["POST"])
router.add_api_route("/{case_id}/escalate", escalate, methods=["POST"])


def _actor(staff: StaffMember) -> Actor:
    return Actor(staff.staff_id, staff.role)


def _keep_until_done(request: Request, task: asyncio.Task[Any]) -> None:
    running: set[asyncio.Task[Any]] = request.app.state.running
    running.add(task)
    task.add_done_callback(running.discard)


async def _release_when_done(lock: asyncio.Lock, work: Awaitable[None]) -> None:
    try:
        await work
    finally:
        lock.release()


async def _batch_sse(events: QueueSink, batch: asyncio.Task[None]) -> AsyncIterator[bytes]:
    while True:
        name, data = await _next_event(events, batch, BATCH_ENDED_EARLY)
        yield _event(name, data)
        if name in FINAL_BATCH_EVENTS:
            return


async def _sse(
    events: QueueSink,
    run: asyncio.Task[RunResult],
    detail: Callable[[], Awaitable[dict[str, Any]]],
) -> AsyncIterator[bytes]:
    while True:
        name, data = await _next_event(events, run, RUN_ENDED_WITHOUT_RESULT)
        if name == "completed":
            yield _event("completed", await detail())
            return
        yield _event(name, data)
        if name == "failed":
            return


async def _next_event(
    events: QueueSink, work: asyncio.Task[Any], ended_early: str
) -> tuple[str, dict[str, Any]]:
    while True:
        if events.queue.empty() and work.done():
            # The work ended without its final event (it crashed): never leave the UI waiting.
            return "failed", {"message": ended_early}
        getter = asyncio.ensure_future(events.queue.get())
        await asyncio.wait({getter, work}, return_when=asyncio.FIRST_COMPLETED)
        if getter.done():
            return getter.result()
        getter.cancel()


def _event(name: str, data: dict[str, Any]) -> bytes:
    return format_sse_event(data_str=json.dumps(data, ensure_ascii=False), event=name)
