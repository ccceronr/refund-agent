"""Model failures, and which manual-review reason any failure becomes (BR-13; R-19, R-20)."""

from sqlalchemy.exc import SQLAlchemyError

from app.rules.model import ReasonCode
from app.tools.queries import CaseDataMissing

DATA_ERRORS = (CaseDataMissing, SQLAlchemyError, OSError)
# A bug rather than an outage: its own code in agent_steps/agent_runs, so it stands out.
UNEXPECTED_ERROR = "UNEXPECTED_ERROR"


class ModelUnavailable(RuntimeError):
    """A model could not answer after its retries (or was switched off by FAULT_INJECTION).

    `reason` is a short code for logs and steps; it never carries response text.
    """

    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(f"{provider} unavailable: {reason}")
        self.provider = provider
        self.reason = reason


def failure_reason(error: Exception) -> ReasonCode | None:
    """Models down → AI_UNAVAILABLE; database or tools down → DATA_UNAVAILABLE; None: a bug."""
    if isinstance(error, ModelUnavailable):
        return ReasonCode.AI_UNAVAILABLE
    if isinstance(error, DATA_ERRORS):
        return ReasonCode.DATA_UNAVAILABLE
    return None


def failure_code(error: Exception) -> str:
    reason = failure_reason(error)
    return reason.value if reason else UNEXPECTED_ERROR
