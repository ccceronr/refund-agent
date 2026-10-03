"""The individual rules BR-01…BR-06 and BR-10 (business-rules.md). Pure functions."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.rules.fees import COVERED_FEE_TYPES, fee_type, fee_type_text, is_fee, is_refund
from app.rules.model import LedgerEntry, StandingFlag

PAST_FRAUD = "PAST_FRAUD"
DEBT_IN_COLLECTIONS = "DEBT_IN_COLLECTIONS"


@dataclass(frozen=True)
class PostingOrderResult:
    qualifies: bool
    opening: Decimal
    credits: Decimal
    debits: Decimal
    credit_after_fee: LedgerEntry | None  # the first qualifying credit posted after the fee


def posting_order(entry: LedgerEntry) -> int:
    """Order within a day: the numeric suffix of posting_ref (YYYYMMDD-NNNN)."""
    return int(entry.posting_ref.rsplit("-", 1)[1])


def covered_by_policy(fee: LedgerEntry) -> bool:
    """BR-01: overdraft (Courtesy Pay) and returned payment (NSF) fees only."""
    return fee_type(fee.description) in COVERED_FEE_TYPES


def qualifies_by_posting_order(
    fee: LedgerEntry, day_postings: Iterable[LedgerEntry]
) -> PostingOrderResult:
    """BR-02: a credit posted after the fee, and the day's deposits would have covered
    the day's payments had they posted first."""
    postings = sorted(day_postings, key=posting_order)
    opening = postings[0].balance_after - postings[0].amount
    credits = [p for p in postings if p.amount > 0 and not is_refund(p)]
    debits = [p for p in postings if p.amount < 0 and not is_fee(p)]
    credit_after = next((c for c in credits if posting_order(c) > posting_order(fee)), None)
    total_credits = sum((c.amount for c in credits), Decimal(0))
    total_debits = sum((d.amount for d in debits), Decimal(0))
    covered = opening + total_credits + total_debits >= 0
    return PostingOrderResult(
        qualifies=credit_after is not None and covered,
        opening=opening,
        credits=total_credits,
        debits=total_debits,
        credit_after_fee=credit_after,
    )


def refunds_in_window(refunds: Iterable[LedgerEntry], as_of: date, *, window_days: int) -> int:
    """BR-03: refunds of any type with as_of - window < date <= as_of."""
    start = as_of - timedelta(days=window_days)
    return sum(1 for r in refunds if is_refund(r) and start < r.date <= as_of)


def within_claim_window(fee: LedgerEntry, as_of: date, *, claim_window_days: int) -> bool:
    """BR-04: as_of - fee date <= claim window (exactly 60 days is still within)."""
    return (as_of - fee.date).days <= claim_window_days


def already_refunded(
    fee: LedgerEntry, *, refunds: Iterable[LedgerEntry], has_refund_action: bool
) -> bool:
    """BR-05: a refund_actions row, or a matching refund transaction on the same
    sub-account, on or after the fee date, for the same amount and fee type text."""
    if has_refund_action:
        return True
    type_text = fee_type_text(fee.description).lower()
    return any(
        is_refund(r)
        and r.sub_account_id == fee.sub_account_id
        and r.amount == -fee.amount
        and r.date >= fee.date
        and type_text in r.description.lower()
        for r in refunds
    )


def in_good_standing(flags: Iterable[StandingFlag]) -> bool:
    """BR-06: any past fraud (resolved or not) or an unresolved debt in collections."""
    return not any(
        f.flag == PAST_FRAUD or (f.flag == DEBT_IN_COLLECTIONS and not f.resolved) for f in flags
    )


def refund_amount(fee: LedgerEntry) -> Decimal:
    """BR-10: always the fee's own amount, from the ledger."""
    return abs(fee.amount)
