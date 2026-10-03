"""Turns read-only tool results into the rules engine's input (business-rules.md).

Shared by the agent flow and by RefundService, which re-checks the rules against the
current ledger inside its own transaction (BR-11 step 1).
"""

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncConnection

from app.rules.model import LedgerEntry, RuleInput, StandingFlag, Thresholds
from app.tools.queries import get_day_postings, get_member_standing, get_refund_history
from app.tools.schemas import CaseContext, FeeCandidate, LedgerTransaction, MemberStanding


def ledger_entry(transaction: LedgerTransaction) -> LedgerEntry:
    t = transaction
    return LedgerEntry(
        t.id, t.sub_account_id, t.date, t.description, t.amount, t.balance_after, t.posting_ref
    )


def refund_lookback_start(as_of: date, thresholds: Thresholds) -> date:
    # BR-03 needs the refund window; BR-05 needs refunds on/after the fee, which is newer.
    return as_of - timedelta(days=thresholds.refund_window_days)


def fee_lookback_start(as_of: date, thresholds: Thresholds) -> date:
    # business-rules.md "Fee candidates": twice the claim window, so BR-04 can explain.
    return as_of - timedelta(days=thresholds.claim_window_days * 2)


def to_rule_input(
    *,
    first_name: str,
    as_of: date,
    fee: FeeCandidate,
    day_postings: list[LedgerTransaction],
    refunds: list[LedgerTransaction],
    standing: MemberStanding,
) -> RuleInput:
    return RuleInput(
        first_name=first_name,
        as_of=as_of,
        fee=ledger_entry(fee.transaction),
        day_postings=tuple(ledger_entry(p) for p in day_postings),
        refunds=tuple(ledger_entry(r) for r in refunds),
        fee_has_refund_action=fee.has_refund_action,
        flags=tuple(StandingFlag(f.flag, f.resolved_at is not None) for f in standing.flags),
    )


async def read_rule_input(
    connection: AsyncConnection,
    case: CaseContext,
    fee: FeeCandidate,
    thresholds: Thresholds,
    *,
    refunds_until: date,
) -> RuleInput:
    """Reads everything the rules need for one fee, on the given connection."""
    as_of, member_id = case.as_of.date(), case.member_id
    day = await get_day_postings(connection, fee.transaction.sub_account_id, fee.transaction.date)
    since = refund_lookback_start(as_of, thresholds)
    refunds = await get_refund_history(connection, member_id, since=since, until=refunds_until)
    standing = await get_member_standing(connection, member_id)
    return to_rule_input(
        first_name=case.first_name,
        as_of=as_of,
        fee=fee,
        day_postings=day,
        refunds=refunds,
        standing=standing,
    )
