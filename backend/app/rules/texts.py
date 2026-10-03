"""Plain-language texts shown to Luis, produced by code, never by a model (R-09, BR-13).

ui.md §3: friendly and direct, no internal terms, no gendered pronouns (repeat the name).
"""

from datetime import date
from decimal import Decimal

from app.rules.checks import PostingOrderResult
from app.rules.fees import PAYROLL_SUFFIX, plain_name
from app.rules.model import Check, FeeType, ReasonCode, Thresholds

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

_MANUAL_REASONS = {
    ReasonCode.INJECTION_SUSPECTED: "This message includes instructions aimed at our system. Please read it yourself before acting.",
    ReasonCode.INTENT_UNCLEAR: "I couldn't tell what {name} is asking for.",
    ReasonCode.NO_FEE_FOUND: "I couldn't find a fee on {name}'s accounts in the last {days} days.",
    ReasonCode.AMBIGUOUS_FEE: "{name} has more than one recent fee and I can't tell which one {name} means.",
    ReasonCode.FEE_TYPE_NOT_COVERED: "This kind of fee isn't covered by the refund policy, so it's your call.",
    ReasonCode.AI_UNAVAILABLE: "The assistant wasn't available, so this case wasn't prepared. Try again, or handle it yourself.",
    ReasonCode.TIMEOUT: "Preparing this case took too long. Try again, or handle it yourself.",
    ReasonCode.DATA_UNAVAILABLE: "I couldn't read {name}'s account information. Try again in a moment.",
    ReasonCode.REJECTED_BY_STAFF: "You rejected the suggestion. Handle this one yourself.",
}  # fmt: skip

_SUPERVISOR_BECAUSE = {
    ReasonCode.LIMIT_REACHED: "{name} has already used every refund available this year",
    ReasonCode.OUT_OF_WINDOW: "the fee is more than {days} days old",
    ReasonCode.NOT_GOOD_STANDING: "{name} isn't in good standing",
    ReasonCode.NO_QUALIFYING_REASON: "the deposits that day wouldn't have covered the payment",
}

NO_FEE_MESSAGE = "No fee was identified for this case, so it can't be refunded here."
ALREADY_REFUNDED_MESSAGE = "This fee was already refunded, so it can't be refunded again."


def money(amount: Decimal) -> str:
    return f"${amount:,.2f}"


def day(on: date) -> str:
    """ "Mon, Sep 14", independent of the server locale."""
    return f"{_WEEKDAYS[on.weekday()]}, {_MONTHS[on.month - 1]} {on.day}"


def manual_reason_text(code: ReasonCode, first_name: str, thresholds: Thresholds) -> str:
    return _MANUAL_REASONS[code].format(name=first_name, days=thresholds.claim_window_days)


def supervisor_needed_text(reason: ReasonCode, first_name: str, thresholds: Thresholds) -> str:
    because = _SUPERVISOR_BECAUSE[reason].format(name=first_name, days=thresholds.claim_window_days)
    return f"This refund needs a supervisor's approval because {because}."


def above_staff_limit_text(thresholds: Thresholds) -> str:
    limit = money(thresholds.staff_approval_limit)
    return f"This refund needs a supervisor's approval because it's more than {limit}."


def posting_order_check(name: str, fee_day: date, result: PostingOrderResult) -> Check:
    if result.qualifies and result.credit_after_fee is not None:
        credit = result.credit_after_fee
        kind = "paycheck" if credit.description.endswith(PAYROLL_SUFFIX) else "deposit"
        text = f"{name}'s {kind} of {money(credit.amount)} arrived the same day and would have covered the payment."
        return Check("BR-02", ok=True, text=text)
    if result.credit_after_fee is None:
        text = f"No deposit arrived after the fee on {day(fee_day)}, so the order of payments didn't cause it."
    else:
        text = f"The deposits on {day(fee_day)} wouldn't have covered that day's payments, even if they had come first."
    return Check("BR-02", ok=False, text=text)


def claim_window_check(name: str, fee_day: date, within: bool, thresholds: Thresholds) -> Check:
    days = thresholds.claim_window_days
    if within:
        return Check("BR-04", ok=True, text=f"Request made within {days} days of the fee.")
    return Check(
        "BR-04",
        ok=False,
        text=f"The fee is from {day(fee_day)}, more than {days} days before {name} asked.",
    )


def standing_check(name: str, good: bool, past_fraud: bool) -> Check:
    if good:
        return Check("BR-06", ok=True, text=f"{name} is in good standing.")
    problem = "a fraud record on file" if past_fraud else "a debt in collections"
    return Check(
        "BR-06", ok=False, text=f"{name} has {problem}, so the refund policy doesn't apply."
    )


def refund_limit_check(name: str, used: int, left_after: int, thresholds: Thresholds) -> Check:
    limit = thresholds.refund_limit_per_window
    if used >= limit:
        return Check(
            "BR-03",
            ok=False,
            text=f"{name} has already used all {limit} refunds available this year.",
        )
    if left_after == 0:
        return Check(
            "BR-03",
            ok=True,
            warning=True,
            text=f"This is {name}'s last refund available this year.",
        )
    return Check("BR-03", ok=True, text=f"{name} has used {used} of {limit} refunds this year.")


def already_refunded_check(refunded: bool) -> Check:
    if refunded:
        return Check("BR-05", ok=False, text="This fee was already refunded.")
    return Check("BR-05", ok=True, text="This fee hasn't been refunded before.")


def coverage_check(kind: FeeType, covered: bool) -> Check:
    if kind is FeeType.OTHER:
        return Check("BR-01", ok=False, text="This kind of fee isn't covered by the refund policy.")
    plural = plain_name(kind).capitalize() + "s"
    verb = "are" if covered else "aren't"
    return Check("BR-01", ok=covered, text=f"{plural} {verb} covered by the refund policy.")
