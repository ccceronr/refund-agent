"""Eval runner (R-24; seed-and-evals §3): the real flow, dry run, over evals/cases/*.json.

    make evals                         real Jev + Anthropic calls (paid)
    make evals ARGS="--record"         real calls, and saves evals/fixtures/ for CI
    make evals ARGS="--offline"        replays evals/fixtures/ (no keys, no cost)
    make evals ARGS="--case E05"       one case

Every run reloads a throwaway database (EVAL_DATABASE_ADMIN_URL, e.g. refunds_eval) from
the seed, so results never depend on the local demo data. Nothing is written but the
eval runs and their steps (tagged is_eval): no proposal, refund, message or status change.
Exit code 1 when the pass rate is below EVAL_MIN_PASS_RATE (default 0.9).
"""

import argparse
import asyncio
import json
import os
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from eval_checks import ALL_CHECKS, Checks, actual_values, check_case, passed
from eval_db import prepare
from eval_fixtures import (
    Recording,
    RecordingDecider,
    RecordingWriter,
    ReplayDecider,
    ReplayWriter,
)

from app.agents.clients import anthropic_client, jev_http_client
from app.agents.decider import Decider
from app.agents.graph import ReplyWriter
from app.agents.run_case import eval_runner, flow_models
from app.agents.steps import StepRecord
from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.pricing import TokenUsage, cost_usd
from app.db.bootstrap_roles import RolePasswords
from app.db.engines import create_ro_engine, create_rw_engine
from app.services.finalize import DryRunFinalizer
from app.services.runs import EvalRunStore

CASES = Path(__file__).parent / "cases"
DEFAULT_MIN_PASS_RATE = 0.9
SYMBOLS = {True: "✓", False: "✗", None: "-"}


@dataclass(frozen=True)
class EvalCase:
    id: str
    description: str
    conversation_id: int
    message_override: str | None
    expected: dict[str, Any]


@dataclass(frozen=True)
class CaseResult:
    case: EvalCase
    checks: Checks
    actual: dict[str, Any]
    latency_ms: int
    cost: Decimal
    baseline: Decimal


def load_cases(only: str | None) -> list[EvalCase]:
    cases = [EvalCase(**json.loads(path.read_text())) for path in sorted(CASES.glob("*.json"))]
    return [case for case in cases if only is None or case.id.startswith(only)]


class Models:
    """Where the model answers come from: live, live and recorded, or replayed."""

    def __init__(self, mode: str, live: tuple[Decider, ReplyWriter] | None) -> None:
        self.mode, self._live = mode, live

    def for_case(self, case_id: str) -> tuple[Decider, ReplyWriter, Recording | None]:
        if self.mode == "offline":
            recording = Recording.load(case_id)
            return ReplayDecider(recording), ReplayWriter(recording), None
        assert self._live is not None  # noqa: S101 - live and record modes always build them
        decider, writer = self._live
        if self.mode == "live":
            return decider, writer, None
        recording = Recording()
        return RecordingDecider(decider, recording), RecordingWriter(writer, recording), recording


async def run_case(case: EvalCase, settings: Settings, models: Models) -> CaseResult:
    decider, writer, recording = models.for_case(case.id)
    ro, rw = create_ro_engine(settings), create_rw_engine(settings)
    runner = eval_runner(
        settings=settings, ro_engine=ro, rw_engine=rw, decider=decider, writer=writer
    )
    started = time.perf_counter()
    try:
        await runner.run(case.conversation_id, message_override=case.message_override)
    finally:
        await ro.dispose()
        await rw.dispose()
    latency_ms = round((time.perf_counter() - started) * 1000)
    if recording is not None:
        recording.save(case.id)
    assert isinstance(runner.finalizer, DryRunFinalizer)  # noqa: S101 - eval runs are dry runs
    assert runner.finalizer.plan is not None  # noqa: S101 - every run ends with a plan
    assert isinstance(runner.store, EvalRunStore)  # noqa: S101
    plan, steps = runner.finalizer.plan, runner.store.steps
    return CaseResult(
        case=case,
        checks=check_case(case.expected, plan),
        actual=actual_values(plan),
        latency_ms=latency_ms,
        cost=sum((step.cost_usd or Decimal(0) for step in steps), Decimal(0)),
        baseline=baseline_cost(steps, settings.anthropic_writer_model),
    )


def baseline_cost(steps: Sequence[StepRecord], writer_model: str) -> Decimal:
    """design §9 / R-24: every model step priced at the writer's rates with the same token
    counts (an estimate: tokenizers differ)."""
    total = Decimal(0)
    for step in steps:
        if step.model is None or step.cost_usd is None:
            continue
        if step.kind == "writer":
            total += step.cost_usd
            continue
        usage = TokenUsage(
            input_tokens=step.input_tokens or 0, output_tokens=step.output_tokens or 0
        )
        total += cost_usd(writer_model, usage)
    return total


def print_report(
    results: list[CaseResult], min_pass_rate: float, writer_model: str, offline: bool
) -> float:
    header = ["case", "conv", *(name[:6] for name in ALL_CHECKS), "ms", "cost"]
    print("  ".join(f"{h:>6}" for h in header))
    for result in results:
        marks = [SYMBOLS[result.checks[name]] for name in ALL_CHECKS]
        row = [result.case.id.split("-")[0], str(result.case.conversation_id), *marks,
               str(result.latency_ms), f"{result.cost:.5f}"]  # fmt: skip
        print("  ".join(f"{cell:>6}" for cell in row))
    print_failures(results)
    rate = print_summary(results, min_pass_rate, writer_model)
    if offline:
        print(
            "Offline: answers replayed from evals/fixtures; latency is not model time, cost is as recorded."
        )
    return rate


def print_failures(results: list[CaseResult]) -> None:
    failures = [(r, name) for r in results for name, ok in r.checks.items() if ok is False]
    if not failures:
        return
    print("\nFailures:")
    for result, name in failures:
        expected = result.case.expected.get(name)
        wanted = f"expected {expected}, " if expected is not None else ""
        print(f"  {result.case.id} {name}: {wanted}got {result.actual.get(name)}")


def print_summary(results: list[CaseResult], min_pass_rate: float, writer_model: str) -> float:
    total = len(results)
    rate = sum(passed(r.checks) for r in results) / total if total else 0.0
    print(
        f"\nCases passed: {sum(passed(r.checks) for r in results)}/{total} ({rate:.1%}); minimum {min_pass_rate:.0%}"
    )
    per_check = []
    for name in ALL_CHECKS:
        applied = [r.checks[name] for r in results if r.checks[name] is not None]
        if applied:
            per_check.append(f"{name} {sum(applied)}/{len(applied)}")
    print("Per check: " + " · ".join(per_check))
    latencies = [r.latency_ms for r in results]
    print(f"Latency: avg {sum(latencies) / total / 1000:.1f} s · max {max(latencies) / 1000:.1f} s")
    cost, baseline = sum(r.cost for r in results), sum(r.baseline for r in results)
    print(f"Cost: avg ${cost / total:.5f} per case · total ${cost:.4f}")
    savings = (1 - cost / baseline) if baseline else Decimal(0)
    print(f"Baseline (every model step priced as {writer_model}, same tokens; an estimate): "
          f"${baseline:.4f} → savings {savings:.0%}")  # fmt: skip
    return rate


async def main(args: argparse.Namespace) -> int:
    configure_logging(sys.stderr)  # stdout carries only the report
    admin_url = os.environ.get("EVAL_DATABASE_ADMIN_URL")
    if not admin_url:
        print("Set EVAL_DATABASE_ADMIN_URL (make evals does it).", file=sys.stderr)
        return 2
    passwords = RolePasswords(
        app_rw=os.environ["APP_RW_PASSWORD"], agent_ro=os.environ["AGENT_RO_PASSWORD"]
    )
    rw, ro = await prepare(admin_url, passwords)
    settings = Settings(app_env="local", database_url_rw=rw, database_url_ro=ro, fault_injection="")
    mode = "offline" if args.offline else "record" if args.record else "live"
    cases = load_cases(args.case)
    if mode == "offline":
        results = [await run_case(case, settings, Models(mode, None)) for case in cases]
    else:
        async with jev_http_client(settings) as http:
            models = Models(mode, flow_models(settings, http, anthropic_client(settings)))
            results = [await run_case(case, settings, models) for case in cases]
    min_rate = float(os.environ.get("EVAL_MIN_PASS_RATE", DEFAULT_MIN_PASS_RATE))
    rate = print_report(results, min_rate, settings.anthropic_writer_model, mode == "offline")
    return 0 if rate >= min_rate else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--offline", action="store_true", help="replay evals/fixtures (no API calls)"
    )
    modes.add_argument("--record", action="store_true", help="real calls; save evals/fixtures")
    parser.add_argument("--case", help="only the cases whose id starts with this, e.g. E05")
    sys.exit(asyncio.run(main(parser.parse_args())))
