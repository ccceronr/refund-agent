"""Runs the flow for one case (R-03, R-16, R-20; design §5.2).

Usage: python -m app.agents.run_case 5012 [--dry-run]
A dry run calls the real models but writes nothing: no proposal, refund, message or step.
"""

import argparse
import asyncio
import json
import sys
import time
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

import anthropic
import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agents.clients import (
    active_fault,
    anthropic_client,
    build_decider,
    build_writer,
    jev_http_client,
)
from app.agents.decider import Decider, Decisions, State
from app.agents.errors import UNEXPECTED_ERROR, failure_reason
from app.agents.graph import FlowDeps, ReplyWriter, build_graph
from app.agents.proposal import build_plan
from app.agents.questions import Question
from app.agents.state import Exit, FinalOutcome, RunState
from app.agents.steps import EventSink, NullSink, StepRecord, StepTracker
from app.core.clock import LocalClock
from app.core.config import Settings
from app.core.logging import configure_logging, error_trace
from app.db.engines import create_ro_engine, create_rw_engine
from app.rules.model import ReasonCode, Thresholds
from app.rules.texts import manual_reason_text
from app.services.finalize import DbFinalizer, DryRunFinalizer, Finalizer
from app.services.refunds import RefundService
from app.services.runs import DbRunStore, MemoryRunStore, RunStore

FAILED_RUN_REASONS = frozenset(
    {ReasonCode.AI_UNAVAILABLE, ReasonCode.DATA_UNAVAILABLE, ReasonCode.TIMEOUT}
)

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RunResult:
    run_id: uuid.UUID
    outcome: FinalOutcome
    final_state: RunState


class CaseRunner:
    def __init__(
        self,
        *,
        settings: Settings,
        ro_engine: AsyncEngine,
        rw_engine: AsyncEngine | None,
        decider: Decider,
        writer: ReplyWriter,
        events: EventSink | None = None,
    ) -> None:
        """Without an app_rw engine the run is a dry run: real models, no writes."""
        self._settings = settings
        self._thresholds = Thresholds.from_settings(settings)
        self._ro = ro_engine
        self._rw = rw_engine
        self._decider = decider
        self._writer = writer
        self._events = events or NullSink()
        clock = LocalClock(settings.local_timezone)
        self.finalizer: Finalizer = (
            DryRunFinalizer()
            if rw_engine is None
            else DbFinalizer(
                rw_engine,
                RefundService(self._thresholds, today=clock.today),
                clock,
            )
        )
        self.store: RunStore = (
            MemoryRunStore()
            if rw_engine is None
            else DbRunStore(rw_engine, settings.max_runs_per_case_per_hour)
        )

    async def run(self, case_id: int, request_id: str | None = None) -> RunResult:
        return await self.execute(case_id, await self.claim(case_id, request_id))

    async def claim(self, case_id: int, request_id: str | None = None) -> uuid.UUID:
        """Marks the case as running. Raises before any work starts (404, 409, 429)."""
        run_id = uuid.uuid4()
        await self.store.start(case_id, run_id, request_id)
        return run_id

    async def execute(self, case_id: int, run_id: uuid.UUID) -> RunResult:
        tracker = StepTracker(run_id, self._events, self.store)
        deps = FlowDeps(
            self._settings,
            self._thresholds,
            self._ro,
            self._decider,
            self._writer,
            tracker,
            self.finalizer,
        )
        started = time.perf_counter()
        state, error_code = await self._run_flow(deps, RunState(case_id=case_id, run_id=run_id))
        if state.outcome is None:
            raise RuntimeError(f"run for case {case_id} ended without an outcome")
        await self.store.finish(
            run_id,
            status="failed" if error_code else "completed",
            error_code=error_code,
            cost=tracker.total_cost,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
        await self._emit_end(case_id, state.outcome, state)
        return RunResult(run_id, state.outcome, state)

    async def _run_flow(self, deps: FlowDeps, state: RunState) -> tuple[RunState, str | None]:
        """The final state and the run's error code (None when the run completed)."""
        try:
            state = await self._run_graph(deps, state)
        except TimeoutError:
            state = await self._end_early(state, ReasonCode.TIMEOUT)
        except Exception as error:
            reason = failure_reason(error)
            if reason is None:
                # A bug, not an outage: still manual review (BR-13), with the trace in the log.
                log.error(
                    "run_crashed",
                    case_id=state.case_id,
                    run_id=str(state.run_id),
                    **error_trace(error),
                )
                return await self._end_early(state, ReasonCode.AI_UNAVAILABLE), UNEXPECTED_ERROR
            state = await self._end_early(state, reason)
        reason = state.exit.reason if state.exit else None
        if reason is not None and reason in FAILED_RUN_REASONS:
            return state, reason.value
        return state, None

    async def _run_graph(self, deps: FlowDeps, state: RunState) -> RunState:
        graph = build_graph(deps)
        async with asyncio.timeout(self._settings.run_timeout_seconds):  # R-20: 90 s per run
            async for values in graph.astream(state, stream_mode="values"):
                state = RunState.model_validate(values)  # the latest state survives a timeout
        return state

    async def _end_early(self, state: RunState, reason: ReasonCode) -> RunState:
        """Timeout or crash: the case still gets a manual-review proposal with the reason."""
        ended = state.model_copy(update={"exit": Exit("manual", reason)})
        outcome = await self.finalizer.finalize(
            state.case_id, state.run_id, build_plan(ended, self._thresholds)
        )
        return ended.model_copy(update={"outcome": outcome})

    async def _emit_end(self, case_id: int, outcome: FinalOutcome, state: RunState) -> None:
        reason = state.exit.reason if state.exit else None
        if reason in {ReasonCode.TIMEOUT, ReasonCode.AI_UNAVAILABLE} and reason is not None:
            name = state.case.first_name if state.case else "the member"
            await self._events.emit(
                "failed", {"message": manual_reason_text(reason, name, self._thresholds)}
            )
            return
        # P6 replaces this payload with the full case detail (design §4.4).
        await self._events.emit("completed", {"case_id": case_id, "status": outcome.case_status})


def flow_models(
    settings: Settings, http: httpx.AsyncClient, claude: anthropic.AsyncAnthropic
) -> tuple[Decider, ReplyWriter]:
    """The decider (Jev, Haiku fallback) and the writer, with FAULT_INJECTION applied."""
    decider: Decider = build_decider(settings, http, claude)
    if active_fault(settings) == "slow":
        decider = SlowDecider(decider, settings.run_timeout_seconds + 1)
    return decider, build_writer(settings, claude)


class SlowDecider:
    """FAULT_INJECTION=slow: answers only after the run timeout, to demo TIMEOUT."""

    def __init__(self, inner: Decider, delay_seconds: float) -> None:
        self._inner = inner
        self._delay = delay_seconds

    async def decide(self, state: State, questions: Mapping[str, Question]) -> Decisions:
        await asyncio.sleep(self._delay)
        return await self._inner.decide(state, questions)


async def _cli(case_id: int, dry_run: bool) -> dict[str, Any]:
    configure_logging(sys.stderr)  # stdout carries only the JSON report
    settings = Settings()
    ro, rw = create_ro_engine(settings), None if dry_run else create_rw_engine(settings)
    claude = anthropic_client(settings)
    try:
        async with jev_http_client(settings) as http:
            decider, writer = flow_models(settings, http, claude)
            runner = CaseRunner(
                settings=settings, ro_engine=ro, rw_engine=rw, decider=decider, writer=writer
            )
            result = await runner.run(case_id)
    finally:
        await ro.dispose()
        if rw is not None:
            await rw.dispose()
    plan = runner.finalizer.plan if isinstance(runner.finalizer, DryRunFinalizer) else None
    steps = runner.store.steps if isinstance(runner.store, MemoryRunStore) else []
    return {
        "case_id": case_id,
        "dry_run": dry_run,
        "outcome": asdict(result.outcome),
        "steps": [_step_summary(step) for step in steps],
        "proposal": json.loads(json.dumps(asdict(plan), default=str)) if plan else None,
    }


def _step_summary(step: StepRecord) -> dict[str, Any]:
    return {
        "label": step.label,
        "status": step.status,
        "ms": step.latency_ms,
        "model": step.model,
        "cost_usd": str(step.cost_usd),
        "fallback": step.used_fallback,
        "error": step.error_code,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.agents.run_case", description=__doc__)
    parser.add_argument("case_id", type=int)
    parser.add_argument("--dry-run", action="store_true", help="real model calls, no writes")
    args = parser.parse_args(argv)
    report = asyncio.run(_cli(args.case_id, args.dry_run))
    sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
