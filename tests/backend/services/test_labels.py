"""Plain-language labels for the UI (ui.md §2.3, §2.4, §3). Pure functions."""

from decimal import Decimal

import pytest

from app.rules.model import Role
from app.services import labels


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        ("Withdrawal Debit Card CITY POWER & LIGHT", "Card payment · City Power & Light"),
        ("Deposit ACH ACME LOGISTICS*PAYROLL", "Paycheck · Acme Logistics"),
        ("Withdrawal ACH CITY WATER", "Payment · City Water"),
        ("Fee Withdrawal ; Courtesy Pay fee", "Overdraft fee"),
        ("Deposit Fee Refund Out of Network ATM Fee", "Out-of-network ATM fee refund"),
        ("Something the core invented", "Something the core invented"),
    ],
)
def test_core_descriptions_read_like_luis_would_say_them(raw: str, shown: str) -> None:
    assert labels.display_description(raw) == shown


def test_headlines_name_the_amount_and_the_fee() -> None:
    assert (
        labels.headline("ready", "REFUND", Decimal("35.00"), "Overdraft fee")
        == "Refund the $35.00 overdraft fee"
    )
    assert (
        labels.headline("ready", "NO_REFUND", Decimal("35.00"), "Overdraft fee")
        == "Don't refund the $35.00 overdraft fee"
    )
    assert labels.headline("manual_review", "MANUAL", None, "fee") == "This one needs your review"


def test_the_authority_line_depends_on_who_is_looking() -> None:
    assert (
        labels.authority_note("needs_supervisor", "SUPERVISOR", Role.STAFF, Decimal("60.00"), "Ana")
        == "A supervisor needs to approve this."
    )
    assert (
        labels.authority_note(
            "needs_supervisor", "SUPERVISOR", Role.SUPERVISOR, Decimal("60.00"), "Ana"
        )
        == "You can approve this."
    )
    assert labels.authority_note("manual_review", "MANUAL", Role.STAFF, None, "Ana") is None
