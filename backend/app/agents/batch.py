"""Prepares every new case, one after another (R-03, "Prepare new messages").

In production the agent would run when each message arrives; the demo prepares new
cases when Luis opens one or asks for all of them at once.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.agents.run_case import CaseRunner
from app.agents.steps import EventSink, NullSink
from app.services.errors import CaseAlreadyDecided, CaseNotFound, RunInProgress, RunLimitReached
from app.services.labels import status_label

# Someone else is on it, it was decided meanwhile, or it hit its hourly run limit (LLM10).
SKIPPED_BECAUSE = (RunInProgress, CaseAlreadyDecided, CaseNotFound, RunLimitReached)
SKIPPED = "skipped"


@dataclass(frozen=True)
class NewCase:
    case_id: int
    member_name: str


async def prepare_cases(
    cases: Sequence[NewCase], runners: Callable[[EventSink], CaseRunner], events: EventSink
) -> None:
    prepared = 0
    for index, case in enumerate(cases, 1):
        progress = {"index": index, "total": len(cases), "case_id": case.case_id,
                    "member_name": case.member_name}  # fmt: skip
        await events.emit("case", {**progress, "status": "running"})
        status = await _prepare(case.case_id, runners)
        prepared += status != SKIPPED
        label = "Skipped" if status == SKIPPED else status_label(status)
        await events.emit("case", {**progress, "status": status, "status_label": label})
    summary = {"total": len(cases), "prepared": prepared, "skipped": len(cases) - prepared}
    await events.emit("done", summary)


async def _prepare(case_id: int, runners: Callable[[EventSink], CaseRunner]) -> str:
    try:
        result = await runners(NullSink()).run(case_id)
    except SKIPPED_BECAUSE:
        return SKIPPED
    return result.outcome.case_status
