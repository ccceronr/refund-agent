"""Fee types and the individual checks BR-01…BR-06, BR-10 (business-rules.md)."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.rules.checks import (
    already_refunded,
    covered_by_policy,
    in_good_standing,
    qualifies_by_posting_order,
    refund_amount,
    refunds_in_window,
    within_claim_window,
)
from app.rules.fees import fee_type, is_fee, is_refund, plain_name
from app.rules.model import FeeType, LedgerEntry, StandingFlag

D = Decimal
DAY = date(2026, 9, 14)


def entry(
    ref: int, description: str, amount: str, balance_after: str, *, on: date = DAY, sub: int = 1302
) -> LedgerEntry:
    return LedgerEntry(
        1000 + ref, sub, on, description, D(amount), D(balance_after), f"{on:%Y%m%d}-{ref:04d}"
    )


FEE = entry(5, "Fee Withdrawal ; Courtesy Pay fee", "-35.00", "-75.00")


@pytest.mark.parametrize(
    ("description", "expected", "name"),
    [
        ("Fee Withdrawal ; Courtesy Pay fee", FeeType.COURTESY_PAY, "overdraft fee"),
        ("Fee Withdrawal ; NSF fee", FeeType.NSF, "returned payment fee"),
        ("Fee Withdrawal ; Returned item fee", FeeType.NSF, "returned payment fee"),
        (
            "Fee Withdrawal ; Out of Network ATM fee",
            FeeType.OUT_OF_NETWORK_ATM,
            "out-of-network ATM fee",
        ),
        (
            "Fee Withdrawal ; Excess Withdrawal Fee",
            FeeType.EXCESS_WITHDRAWAL,
            "savings withdrawal fee",
        ),
        ("Fee Withdrawal ; Paper statement fee", FeeType.OTHER, "fee"),
        ("Fee Withdrawal ;   COURTESY PAY FEE  ", FeeType.COURTESY_PAY, "overdraft fee"),
    ],
)
def test_fee_type_comes_from_the_text_after_the_semicolon(
    description: str, expected: FeeType, name: str
) -> None:
    assert fee_type(description) is expected
    assert plain_name(expected) == name


@pytest.mark.parametrize(
    ("description", "amount", "fee", "refund"),
    [
        ("Fee Withdrawal ; Courtesy Pay fee", "-35.00", True, False),
        ("Fee Withdrawal ; Courtesy Pay fee", "35.00", False, False),
        ("Deposit Fee Refund Courtesy Pay Fee", "35.00", False, True),
        ("Deposit Fee Refund Courtesy Pay Fee", "-35.00", False, False),
        ("Deposit ACH ACME LOGISTICS*PAYROLL", "1400.00", False, False),
    ],
)
def test_fee_and_refund_transactions_need_both_sign_and_prefix(
    description: str, amount: str, fee: bool, refund: bool
) -> None:
    transaction = entry(0, description, amount, "0")

    assert is_fee(transaction) is fee
    assert is_refund(transaction) is refund


@pytest.mark.parametrize(
    ("description", "covered"),
    [
        ("Fee Withdrawal ; Courtesy Pay fee", True),
        ("Fee Withdrawal ; NSF fee", True),
        ("Fee Withdrawal ; Out of Network ATM fee", False),
        ("Fee Withdrawal ; Excess Withdrawal Fee", False),
        ("Fee Withdrawal ; Paper statement fee", False),
    ],
)
def test_br01_only_overdraft_and_returned_payment_fees_are_covered(
    description: str, covered: bool
) -> None:
    assert covered_by_policy(replace(FEE, description=description)) is covered


def test_br02_ana_qualifies_with_the_spec_numbers() -> None:
    day = (
        entry(0, "Withdrawal Debit Card CITY POWER & LIGHT", "-60.00", "-40.00"),
        FEE,
        entry(10, "Deposit ACH ACME LOGISTICS*PAYROLL", "1400.00", "1325.00"),
    )

    result = qualifies_by_posting_order(FEE, day)

    assert (result.opening, result.credits, result.debits) == (
        D("20.00"),
        D("1400.00"),
        D("-60.00"),
    )
    assert result.qualifies


def test_br02_sofia_does_not_qualify_without_a_deposit_that_day() -> None:
    fee = entry(5, "Fee Withdrawal ; Courtesy Pay fee", "-35.00", "-38.99")
    day = (entry(0, "Withdrawal ACH STREAMFLIX", "-15.99", "-3.99"), fee)

    assert not qualifies_by_posting_order(fee, day).qualifies


def test_br02_ethan_does_not_qualify_when_payroll_lands_the_next_day() -> None:
    fee = entry(5, "Fee Withdrawal ; Courtesy Pay fee", "-35.00", "-105.00", on=date(2026, 9, 21))
    day = (
        entry(
            0, "Withdrawal Debit Card CORNER PHARMACY", "-120.00", "-70.00", on=date(2026, 9, 21)
        ),
        fee,
    )

    assert not qualifies_by_posting_order(fee, day).qualifies


def test_br02_a_deposit_posted_before_the_fee_does_not_count() -> None:
    # The day's sum is fine (20 + 1400 - 60 >= 0); only "credit after the fee" fails.
    day = (
        entry(0, "Withdrawal Debit Card SHOP", "-60.00", "-40.00"),
        entry(3, "Deposit ACH JOB*PAYROLL", "1400.00", "1360.00"),
        replace(FEE, balance_after=D("1325.00")),
    )

    result = qualifies_by_posting_order(day[2], day)

    assert result.opening + result.credits + result.debits >= 0
    assert not result.qualifies


def test_br02_a_deposit_too_small_to_cover_the_day_does_not_qualify() -> None:
    day = (
        entry(0, "Withdrawal Debit Card SHOP", "-100.00", "-100.00"),
        replace(FEE, balance_after=D("-135.00")),
        entry(10, "Deposit ACH JOB*PAYROLL", "50.00", "-85.00"),
    )

    result = qualifies_by_posting_order(day[1], day)

    assert result.opening + result.credits + result.debits == D("-50.00")
    assert not result.qualifies


def test_br02_a_refund_posted_after_the_fee_is_not_a_qualifying_credit() -> None:
    day = (
        entry(0, "Withdrawal Debit Card SHOP", "-60.00", "-40.00"),
        replace(FEE, balance_after=D("-75.00")),
        entry(10, "Deposit Fee Refund Courtesy Pay Fee", "35.00", "-40.00"),
    )

    assert not qualifies_by_posting_order(day[1], day).qualifies


def test_br02_uses_posting_order_not_list_order() -> None:
    payroll = entry(10, "Deposit ACH ACME LOGISTICS*PAYROLL", "1400.00", "1325.00")
    bill = entry(0, "Withdrawal Debit Card CITY POWER & LIGHT", "-60.00", "-40.00")

    assert qualifies_by_posting_order(FEE, (payroll, FEE, bill)).qualifies


AS_OF = date(2026, 9, 15)


def refund_on(on: date, sub: int = 1302) -> LedgerEntry:
    return entry(2, "Deposit Fee Refund Courtesy Pay Fee", "35.00", "100.00", on=on, sub=sub)


@pytest.mark.parametrize(
    ("days_before", "counted"),
    [(0, True), (364, True), (365, False), (400, False)],
)
def test_br03_window_counts_refunds_after_as_of_minus_365_days(
    days_before: int, counted: bool
) -> None:
    refunds = (refund_on(AS_OF - timedelta(days=days_before)),)

    assert refunds_in_window(refunds, AS_OF, window_days=365) == (1 if counted else 0)


def test_br03_refunds_after_as_of_are_not_in_the_window() -> None:
    assert refunds_in_window((refund_on(AS_OF + timedelta(days=1)),), AS_OF, window_days=365) == 0


def test_br03_refunds_of_any_fee_type_and_sub_account_count() -> None:
    refunds = (
        refund_on(date(2026, 3, 3)),
        entry(
            2,
            "Deposit Fee Refund Out of Network Fee",
            "5.00",
            "880.45",
            on=date(2026, 1, 20),
            sub=1301,
        ),
    )

    assert refunds_in_window(refunds, AS_OF, window_days=365) == 2


@pytest.mark.parametrize(
    ("days_before", "within"), [(0, True), (59, True), (60, True), (61, False)]
)
def test_br04_claim_window_includes_exactly_60_days(days_before: int, within: bool) -> None:
    fee = replace(FEE, date=AS_OF - timedelta(days=days_before))

    assert within_claim_window(fee, AS_OF, claim_window_days=60) is within


def test_br05_a_refund_action_row_means_already_refunded() -> None:
    assert already_refunded(FEE, refunds=(), has_refund_action=True)


def test_br05_a_matching_refund_transaction_means_already_refunded() -> None:
    assert already_refunded(FEE, refunds=(refund_on(date(2026, 9, 15)),), has_refund_action=False)


def test_br05_a_refund_on_the_fee_day_counts() -> None:
    assert already_refunded(FEE, refunds=(refund_on(DAY),), has_refund_action=False)


@pytest.mark.parametrize(
    "refund",
    [
        refund_on(date(2026, 9, 13)),
        refund_on(date(2026, 9, 15), sub=1301),
        entry(2, "Deposit Fee Refund Courtesy Pay Fee", "30.00", "1", on=date(2026, 9, 15)),
        entry(2, "Deposit Fee Refund NSF fee", "35.00", "1", on=date(2026, 9, 15)),
    ],
    ids=["before-the-fee", "other-sub-account", "other-amount", "other-fee-type"],
)
def test_br05_a_refund_that_does_not_match_the_fee_does_not_count(refund: LedgerEntry) -> None:
    assert not already_refunded(FEE, refunds=(refund,), has_refund_action=False)


@pytest.mark.parametrize(
    ("flags", "good"),
    [
        ((), True),
        ((StandingFlag("PAST_FRAUD", resolved=True),), False),
        ((StandingFlag("PAST_FRAUD", resolved=False),), False),
        ((StandingFlag("DEBT_IN_COLLECTIONS", resolved=False),), False),
        ((StandingFlag("DEBT_IN_COLLECTIONS", resolved=True),), True),
    ],
    ids=["no-flags", "fraud-resolved", "fraud-open", "debt-open", "debt-resolved"],
)
def test_br06_good_standing(flags: tuple[StandingFlag, ...], good: bool) -> None:
    assert in_good_standing(flags) is good


@pytest.mark.parametrize(
    ("amount", "expected"), [("-35.00", "35.00"), ("-5.00", "5.00"), ("-60.25", "60.25")]
)
def test_br10_refund_amount_is_the_fee_amount_from_the_ledger(amount: str, expected: str) -> None:
    assert refund_amount(replace(FEE, amount=D(amount))) == D(expected)
