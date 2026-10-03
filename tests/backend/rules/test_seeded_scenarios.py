"""Seed + tools + rules agree with seed-and-evals §2 "Expected", with no model involved.

Typed decisions are assumed confident Jev answers and a writer draft that passed the
guard, so the tier shown is the best case the flow could reach.
"""

from collections.abc import AsyncIterator, Callable
from datetime import date, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import Settings
from app.db.engines import create_ro_engine
from app.rules.model import (
    AutoSignals,
    LedgerEntry,
    ReasonCode,
    Recommendation,
    RuleInput,
    StandingFlag,
    Thresholds,
    Tier,
    TypedAnswer,
)
from app.rules.outcome import decide_tier, evaluate
from app.tools.queries import (
    find_fee_candidates,
    get_day_postings,
    get_member_standing,
    get_refund_history,
    load_case,
)
from app.tools.schemas import LedgerTransaction

CLEAN = AutoSignals((TypedAnswer("jev", 0.99),), None, 0.02, "writer", True)
R, N, M = Recommendation.REFUND, Recommendation.NO_REFUND, Recommendation.MANUAL


@pytest.fixture
async def ro(
    seeded_db: dict[str, str], make_settings: Callable[..., Settings]
) -> AsyncIterator[AsyncConnection]:
    engine = create_ro_engine(make_settings())
    try:
        async with engine.connect() as connection:
            yield connection
    finally:
        await engine.dispose()


def _entry(t: LedgerTransaction) -> LedgerEntry:
    return LedgerEntry(
        t.id, t.sub_account_id, t.date, t.description, t.amount, t.balance_after, t.posting_ref
    )


async def _rule_input(
    ro: AsyncConnection, conversation_id: int, fee_date: date | None, limits: Thresholds
) -> RuleInput:
    case = await load_case(ro, conversation_id)
    as_of = case.as_of.date()
    lookback = as_of - timedelta(days=limits.claim_window_days * 2)
    candidates = await find_fee_candidates(ro, case.member_id, since=lookback, until=as_of)
    chosen = [c for c in candidates if fee_date is None or c.transaction.date == fee_date]
    assert len(chosen) == 1, f"{conversation_id}: {len(chosen)} candidates"
    fee = chosen[0]
    day = await get_day_postings(ro, fee.transaction.sub_account_id, fee.transaction.date)
    window_start = as_of - timedelta(days=limits.refund_window_days)
    refunds = await get_refund_history(ro, case.member_id, since=window_start, until=as_of)
    standing = await get_member_standing(ro, case.member_id)
    return RuleInput(
        first_name=case.first_name,
        as_of=as_of,
        fee=_entry(fee.transaction),
        day_postings=tuple(_entry(p) for p in day),
        refunds=tuple(_entry(r) for r in refunds),
        fee_has_refund_action=fee.has_refund_action,
        flags=tuple(StandingFlag(f.flag, f.resolved_at is not None) for f in standing.flags),
    )


@pytest.mark.parametrize(
    ("conversation_id", "fee_date", "recommendation", "reason", "tier"),
    [
        (5012, None, R, ReasonCode.ELIGIBLE, Tier.STAFF),
        (5008, None, M, ReasonCode.FEE_TYPE_NOT_COVERED, Tier.MANUAL),
        (5013, None, R, ReasonCode.ELIGIBLE, Tier.AUTO),
        (5014, None, R, ReasonCode.ELIGIBLE, Tier.AUTO),
        (5015, None, N, ReasonCode.LIMIT_REACHED, Tier.STAFF),
        (5016, None, R, ReasonCode.ELIGIBLE, Tier.AUTO),
        (5017, None, N, ReasonCode.NO_QUALIFYING_REASON, Tier.STAFF),
        (5018, None, N, ReasonCode.NO_QUALIFYING_REASON, Tier.STAFF),
        (5019, None, N, ReasonCode.NOT_GOOD_STANDING, Tier.STAFF),
        (5020, None, N, ReasonCode.NOT_GOOD_STANDING, Tier.STAFF),
        (5021, None, R, ReasonCode.ELIGIBLE, Tier.AUTO),
        (5024, date(2026, 9, 21), R, ReasonCode.ELIGIBLE, Tier.AUTO),
        (5025, None, N, ReasonCode.OUT_OF_WINDOW, Tier.STAFF),
        (5026, None, N, ReasonCode.ALREADY_REFUNDED, Tier.STAFF),
        (5028, None, R, ReasonCode.ELIGIBLE, Tier.STAFF),
        (5029, None, R, ReasonCode.ELIGIBLE, Tier.AUTO),
    ],
)
async def test_seeded_scenario_gets_its_expected_outcome(
    ro: AsyncConnection,
    thresholds: Thresholds,
    conversation_id: int,
    fee_date: date | None,
    recommendation: Recommendation,
    reason: ReasonCode,
    tier: Tier,
) -> None:
    evaluation = evaluate(await _rule_input(ro, conversation_id, fee_date, thresholds), thresholds)

    assert (evaluation.recommendation, evaluation.reason_code) == (recommendation, reason)
    assert decide_tier(evaluation, CLEAN, thresholds).tier is tier
