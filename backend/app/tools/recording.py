"""Times every tool call so the run can store it as a step (design §9, R-34).

Tools only read (agent_ro), so they never write steps themselves: the recorder keeps the
calls in memory and the agent run persists them with app_rw (P5).
"""

import time
from collections.abc import Awaitable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ToolCall:
    name: str
    latency_ms: int
    ok: bool
    error: str | None = None


@dataclass
class ToolRecorder:
    calls: list[ToolCall] = field(default_factory=list)

    async def run[T](self, name: str, call: Awaitable[T]) -> T:
        started = time.perf_counter()
        try:
            result = await call
        except Exception as error:
            # Recorded with its type only (no message: it may contain data), then re-raised.
            self.calls.append(
                ToolCall(name, _elapsed_ms(started), ok=False, error=type(error).__name__)
            )
            raise
        self.calls.append(ToolCall(name, _elapsed_ms(started), ok=True))
        return result


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
