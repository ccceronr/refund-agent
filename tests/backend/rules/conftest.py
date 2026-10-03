"""Rule inputs built from the PDF's Ana case (business-rules.md examples), plus thresholds.

Thresholds are written out with the spec defaults, not read from Settings, so a config
change can't silently change what these tests expect.
"""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.rules.model import AutoSignals, LedgerEntry, RuleInput, Thresholds, TypedAnswer

D = Decimal

SPEC_THRESHOLDS = Thresholds(
    refund_limit_per_window=3,
    refund_window_days=365,
    claim_window_days=60,
    staff_approval_limit=D("50.00"),
    auto_refund_enabled=True,
    auto_refund_max_amount=D("35.00"),
    auto_min_confidence=0.95,
    auto_max_injection=0.1,
)

ANA_BILL = LedgerEntry(
    88001,
    1302,
    date(2026, 9, 14),
    "Withdrawal Debit Card CITY POWER & LIGHT",
    D("-60.00"),
    D("-40.00"),
    "20260914-0000",
)
ANA_FEE = LedgerEntry(
    88002,
    1302,
    date(2026, 9, 14),
    "Fee Withdrawal ; Courtesy Pay fee",
    D("-35.00"),
    D("-75.00"),
    "20260914-0005",
)
ANA_PAYROLL = LedgerEntry(
    88003,
    1302,
    date(2026, 9, 14),
    "Deposit ACH ACME LOGISTICS*PAYROLL",
    D("1400.00"),
    D("1325.00"),
    "20260914-0010",
)
ANA_REFUND_MARCH = LedgerEntry(
    87410,
    1302,
    date(2026, 3, 3),
    "Deposit Fee Refund Courtesy Pay Fee",
    D("35.00"),
    D("412.10"),
    "20260303-0002",
)
ANA_REFUND_JANUARY = LedgerEntry(87390, 1301, date(2026, 1, 20), "Deposit Fee Refund Out of Network Fee", D("5.00"), D("880.45"), "20260120-0002")  # fmt: skip


@pytest.fixture
def thresholds() -> Thresholds:
    return SPEC_THRESHOLDS


@pytest.fixture
def ana() -> RuleInput:
    """Ana: same-day paycheck, 2 refunds in the window, good standing → REFUND, last one."""
    return RuleInput(
        first_name="Ana",
        as_of=date(2026, 9, 15),
        fee=ANA_FEE,
        day_postings=(ANA_BILL, ANA_FEE, ANA_PAYROLL),
        refunds=(ANA_REFUND_JANUARY, ANA_REFUND_MARCH),
        fee_has_refund_action=False,
        flags=(),
    )


@pytest.fixture
def ana_with_refunds_left(ana: RuleInput) -> RuleInput:
    """Ana with only the March refund: 1 in the window, so 1 left after this one."""
    return replace(ana, refunds=(ANA_REFUND_MARCH,))


@pytest.fixture
def clean_signals() -> AutoSignals:
    """Every typed decision from Jev and confident, no injection, writer draft passed."""
    return AutoSignals(
        typed_answers=(TypedAnswer("jev", 0.99), TypedAnswer("jev", 0.98)),
        fee_choice=None,
        injection_probability=0.02,
        draft_source="writer",
        guard_passed=True,
    )
