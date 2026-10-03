"""BR-09: who may execute a refund. Checked server-side for every decision (OWASP A01).

Sending a reply without a refund never needs this check.
"""

from app.rules import texts
from app.rules.model import (
    AuthorityDecision,
    Evaluation,
    ReasonCode,
    Recommendation,
    Role,
    Thresholds,
    Verdict,
)

# Refunding against these NO_REFUND reasons is a policy exception: supervisors only.
POLICY_EXCEPTIONS = frozenset(
    {
        ReasonCode.LIMIT_REACHED,
        ReasonCode.OUT_OF_WINDOW,
        ReasonCode.NOT_GOOD_STANDING,
        ReasonCode.NO_QUALIFYING_REASON,
    }
)


def refund_authority(
    role: Role, evaluation: Evaluation | None, first_name: str, thresholds: Thresholds
) -> AuthorityDecision:
    """`evaluation` is None when the case has no identified fee (BR-09 "Manual cases")."""
    if evaluation is None:
        return AuthorityDecision(Verdict.NO_FEE, texts.NO_FEE_MESSAGE)
    if evaluation.reason_code is ReasonCode.ALREADY_REFUNDED:
        return AuthorityDecision(Verdict.NEVER, texts.ALREADY_REFUNDED_MESSAGE)
    why = _why_a_supervisor_is_needed(evaluation, first_name, thresholds)
    if why is None or role is Role.SUPERVISOR:
        return AuthorityDecision(Verdict.ALLOWED, None)
    # Staff, and the automatic flow (system), never have supervisor authority.
    return AuthorityDecision(Verdict.NEEDS_SUPERVISOR, why)


def _why_a_supervisor_is_needed(
    evaluation: Evaluation, first_name: str, thresholds: Thresholds
) -> str | None:
    exception = (
        evaluation.recommendation is Recommendation.NO_REFUND
        and evaluation.reason_code in POLICY_EXCEPTIONS
    )
    if exception:
        return texts.supervisor_needed_text(evaluation.reason_code, first_name, thresholds)
    if evaluation.amount > thresholds.staff_approval_limit:
        return texts.above_staff_limit_text(thresholds)
    return None
