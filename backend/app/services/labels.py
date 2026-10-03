"""Plain-language labels the API returns for the UI (ui.md §2 and §3). Pure: no I/O.

Built by code from templates, never by a model (design §4.2, LLM09).
"""

from decimal import Decimal

from app.rules.fees import FEE_PREFIX, PAYROLL_SUFFIX, REFUND_PREFIX, fee_type, plain_name
from app.rules.model import Role, Tier
from app.rules.texts import money

STATUS_LABELS = {
    "new": "Not prepared yet",
    "running": "Preparing…",
    "ready": "Ready for you",
    "needs_supervisor": "Needs a supervisor",
    "manual_review": "Needs your review",
    "not_refund": "Not a refund request",
    "auto_resolved": "Refunded automatically",
    "resolved": "Done",
}
CARD_PAYMENT_PREFIX = "Withdrawal Debit Card"
BILL_PAYMENT_PREFIX = "Withdrawal ACH"
DEPOSIT_PREFIX = "Deposit ACH"


def status_label(status: str) -> str:
    return STATUS_LABELS[status]


def fee_label(description: str) -> str:
    """ "Fee Withdrawal ; Courtesy Pay fee" → "Overdraft fee"."""
    return _sentence_case(plain_name(fee_type(description)))


def _sentence_case(text: str) -> str:
    # Not str.capitalize(): it would lower-case the rest ("ATM" → "atm").
    return text[:1].upper() + text[1:]


def topic(category: str, fee_description: str | None, subject: str) -> str:
    """The queue's topic (design §4.1)."""
    if category == "other":
        return "Not a refund"
    if fee_description is not None:
        return f"{fee_label(fee_description)} refund"
    return subject


def display_description(description: str) -> str:
    """Core ledger text → what Luis reads (ui.md §2.4); the raw text stays in a tooltip."""
    if description.startswith(FEE_PREFIX):
        return fee_label(description)
    if description.startswith(REFUND_PREFIX):
        return f"{fee_label(description)} refund"
    if description.startswith(CARD_PAYMENT_PREFIX):
        return f"Card payment · {_party(description, CARD_PAYMENT_PREFIX)}"
    if description.startswith(DEPOSIT_PREFIX) and description.endswith(PAYROLL_SUFFIX):
        employer = description.removesuffix(PAYROLL_SUFFIX)
        return f"Paycheck · {_party(employer, DEPOSIT_PREFIX)}"
    if description.startswith(BILL_PAYMENT_PREFIX):
        return f"Payment · {_party(description, BILL_PAYMENT_PREFIX)}"
    return description


def headline(case_status: str, recommendation: str, amount: Decimal | None, fee: str) -> str:
    """The recommendation card's title (ui.md §2.3)."""
    if case_status == "auto_resolved":
        return "Refunded automatically"
    if case_status == "not_refund":
        return "This isn't a refund request"
    if recommendation == "REFUND" and amount is not None:
        return f"Refund the {money(amount)} {fee.lower()}"
    if recommendation == "NO_REFUND" and amount is not None:
        return f"Don't refund the {money(amount)} {fee.lower()}"
    return "This one needs your review"


def authority_note(
    case_status: str, tier: str, viewer: Role, amount: Decimal | None, first_name: str
) -> str | None:
    """Who can act (ui.md §2.3). BR-09 itself is enforced again when Luis acts."""
    if case_status == "auto_resolved" and amount is not None:
        return (
            f"Done — the {money(amount)} is back in {first_name}'s account and the reply was sent."
        )
    if case_status in {"resolved", "not_refund", "manual_review", "new", "running"}:
        return None
    if tier == Tier.SUPERVISOR.value and viewer is not Role.SUPERVISOR:
        return "A supervisor needs to approve this."
    return "You can approve this."


def _party(description: str, prefix: str) -> str:
    return description.removeprefix(prefix).strip().title()
