"""Each node runs as a step: timed, costed, streamed live and persisted (R-16, R-34, design §9).

Steps carry no personal data: ids, codes, counts, tokens and costs only.
"""

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, Protocol

from app.agents.decider import Decisions
from app.agents.errors import failure_code
from app.agents.writer import WrittenReply
from app.tools.recording import ToolRecorder

StepKind = Literal["decision", "tool", "rules", "retrieval", "writer", "guard"]
Provider = Literal["jev", "anthropic", "db", "none"]
StepStatus = Literal["running", "done", "failed"]

# design §5.3: what Luis sees while a case is prepared.
STEP_LABELS = {
    "load_case": "Opening the conversation",
    "screen": "Reading the message",
    "gather_evidence": "Looking at the accounts",
    "identify_fee": "Finding the fee",
    "day_postings": "Checking the order of that day's payments",
    "evaluate_rules": "Checking the refund policy",
    "find_policy": "Finding the policy that applies",
    "draft_reply": "Writing the reply",
    "guard_output": "Double-checking the reply",
    "finalize": "Done",
}


class EventSink(Protocol):
    async def emit(self, event: str, data: dict[str, Any]) -> None: ...


class NullSink:
    async def emit(self, event: str, data: dict[str, Any]) -> None:
        return None


@dataclass
class QueueSink:
    """Feeds the SSE response of POST /cases/{id}/run (design §4.4)."""

    queue: asyncio.Queue[tuple[str, dict[str, Any]]] = field(default_factory=asyncio.Queue)

    async def emit(self, event: str, data: dict[str, Any]) -> None:
        await self.queue.put((event, data))


@dataclass
class StepRecord:
    ordinal: int
    name: str
    label: str
    kind: StepKind
    provider: Provider
    status: StepStatus
    started_at: datetime
    latency_ms: int = 0
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal(0)
    used_fallback: bool = False
    error_code: str | None = None
    output: dict[str, Any] = field(default_factory=dict)

    def add_decisions(self, decisions: Decisions) -> None:
        self.provider = "jev" if decisions.source == "jev" else "anthropic"
        self.model = decisions.model
        self.used_fallback = self.used_fallback or decisions.source == "fallback"
        self._add_usage(
            decisions.usage.input_tokens, decisions.usage.output_tokens, decisions.cost_usd
        )
        if decisions.request_id:
            self.output["request_id"] = decisions.request_id

    def add_reply(self, reply: WrittenReply) -> None:
        self.provider = "anthropic"
        self.model = reply.model
        self._add_usage(reply.usage.input_tokens, reply.usage.output_tokens, reply.cost_usd)
        self.output["cache_read_tokens"] = reply.usage.cache_read_tokens
        self.output["cache_write_tokens"] = reply.usage.cache_write_tokens

    def add_tool_calls(self, recorder: ToolRecorder) -> None:
        self.output["tool_calls"] = [
            {"name": c.name, "latency_ms": c.latency_ms, "ok": c.ok} for c in recorder.calls
        ]

    def fail(self, error_code: str) -> None:
        self.error_code = error_code

    def _add_usage(self, input_tokens: int, output_tokens: int, cost: Decimal) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cost_usd += cost


class StepSink(Protocol):
    async def add_step(self, run_id: uuid.UUID, record: StepRecord) -> None: ...


class StepTracker:
    def __init__(self, run_id: uuid.UUID, events: EventSink, store: StepSink) -> None:
        self._run_id = run_id
        self._events = events
        self._store = store
        self.records: list[StepRecord] = []

    @property
    def total_cost(self) -> Decimal:
        return sum((r.cost_usd for r in self.records), Decimal(0))

    @asynccontextmanager
    async def step(
        self, name: str, kind: StepKind, provider: Provider = "none"
    ) -> AsyncIterator[StepRecord]:
        record = StepRecord(
            ordinal=len(self.records) + 1,
            name=name,
            label=STEP_LABELS[name],
            kind=kind,
            provider=provider,
            status="running",
            started_at=datetime.now(UTC),
        )
        self.records.append(record)
        await self._events.emit("step", {"name": name, "label": record.label, "status": "running"})
        started = time.perf_counter()
        try:
            yield record
        except Exception as error:
            record.error_code = record.error_code or failure_code(error)
            raise
        finally:
            record.latency_ms = round((time.perf_counter() - started) * 1000)
            record.status = "failed" if record.error_code else "done"
            await self._store.add_step(self._run_id, record)
            await self._events.emit(
                "step",
                {
                    "name": name,
                    "label": record.label,
                    "status": record.status,
                    "duration_ms": record.latency_ms,
                },
            )
