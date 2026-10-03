"""Turns declared posting days into transaction rows (seed-and-evals §1).

A scenario declares, per day, the balance before the first posting and the postings in
posting order. This module computes `balance_after` and `posting_ref`, and checks the
seed invariants before anything is written:
  1. within a sub-account and a day, balances chain in posting order;
  2. `posting_ref` is `YYYYMMDD-NNNN`, matches the date and is unique per sub-account;
  3. a new sub-account's balance equals its last `balance_after`.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import pairwise

# Posting numbers step by 5 within a day, like the PDF rows (0000, 0005, 0010).
POSTING_STEP = 5
COURTESY_PAY_FEE_AMOUNT = Decimal("35.00")  # fee-schedule policy
EXCESS_WITHDRAWAL_FEE_AMOUNT = Decimal("5.00")  # fee-schedule policy


class SeedInvariantError(ValueError):
    pass


@dataclass(frozen=True)
class Posting:
    description: str
    amount: Decimal


@dataclass(frozen=True)
class Day:
    date: date
    opening: Decimal
    postings: tuple[Posting, ...]


@dataclass(frozen=True)
class LedgerRow:
    date: date
    description: str
    amount: Decimal
    balance_after: Decimal
    posting_ref: str


def card(merchant: str, amount: str) -> Posting:
    return Posting(f"Withdrawal Debit Card {merchant}", -Decimal(amount))


def ach(biller: str, amount: str) -> Posting:
    return Posting(f"Withdrawal ACH {biller}", -Decimal(amount))


def payroll(employer: str, amount: str) -> Posting:
    return Posting(f"Deposit ACH {employer}*PAYROLL", Decimal(amount))


def courtesy_pay_fee() -> Posting:
    return Posting("Fee Withdrawal ; Courtesy Pay fee", -COURTESY_PAY_FEE_AMOUNT)


def nsf_fee() -> Posting:
    return Posting("Fee Withdrawal ; NSF fee", -COURTESY_PAY_FEE_AMOUNT)


def excess_withdrawal_fee() -> Posting:
    return Posting("Fee Withdrawal ; Excess Withdrawal Fee", -EXCESS_WITHDRAWAL_FEE_AMOUNT)


def courtesy_pay_refund() -> Posting:
    return Posting("Deposit Fee Refund Courtesy Pay Fee", COURTESY_PAY_FEE_AMOUNT)


def post_days(days: tuple[Day, ...]) -> list[LedgerRow]:
    """All rows of one sub-account, oldest day first, invariants checked."""
    rows = [row for day in sorted(days, key=lambda d: d.date) for row in _post_day(day)]
    _check_invariants(rows)
    return rows


def closing_balance(rows: list[LedgerRow]) -> Decimal:
    if not rows:
        raise SeedInvariantError("a sub-account needs at least one posting to have a balance")
    return rows[-1].balance_after


def _post_day(day: Day) -> list[LedgerRow]:
    balance = day.opening
    rows = []
    for position, posting in enumerate(day.postings):
        balance += posting.amount
        posting_ref = f"{day.date:%Y%m%d}-{position * POSTING_STEP:04d}"
        rows.append(LedgerRow(day.date, posting.description, posting.amount, balance, posting_ref))
    return rows


def _check_invariants(rows: list[LedgerRow]) -> None:
    duplicates = [ref for ref, count in Counter(r.posting_ref for r in rows).items() if count > 1]
    if duplicates:
        raise SeedInvariantError(f"duplicate posting_ref in one sub-account: {duplicates}")
    for previous, current in pairwise(rows):
        same_day = previous.date == current.date
        if same_day and current.balance_after != previous.balance_after + current.amount:
            raise SeedInvariantError(f"balance does not chain at {current.posting_ref}")
    for row in rows:
        if row.posting_ref[:8] != f"{row.date:%Y%m%d}":
            raise SeedInvariantError(f"posting_ref {row.posting_ref} does not match {row.date}")
