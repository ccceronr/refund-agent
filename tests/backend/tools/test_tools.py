"""Read-only tools over the seeded data, as agent_ro (tasks P2, R-07, R-10, R-31)."""

from collections.abc import AsyncIterator, Callable
from datetime import date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import Settings
from app.db.engines import create_ro_engine
from app.tools.queries import (
    find_fee_candidates,
    get_day_postings,
    get_member_standing,
    get_refund_history,
    load_case,
    search_policy,
)
from app.tools.recording import ToolRecorder

ANA = 301
ANA_CHECKING = 1302
ANA_AS_OF = date(2026, 9, 15)


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


async def test_load_case_takes_as_of_from_the_latest_member_message(ro: AsyncConnection) -> None:
    case = await load_case(ro, 5011)

    assert case.first_name == "Marcus"
    assert [m.body for m in case.member_messages] == ["My card gets declined at the gas station."]
    assert case.as_of == datetime(2026, 9, 14, 17, 3, 10)


async def test_day_postings_come_in_posting_order(ro: AsyncConnection) -> None:
    postings = await get_day_postings(ro, ANA_CHECKING, date(2026, 9, 14))

    assert [p.posting_ref for p in postings] == ["20260914-0000", "20260914-0005", "20260914-0010"]


async def test_refund_history_spans_every_sub_account_of_the_member(ro: AsyncConnection) -> None:
    refunds = await get_refund_history(ro, ANA, since=date(2025, 9, 15), until=ANA_AS_OF)

    assert sorted(r.sub_account_id for r in refunds) == [1301, 1302]


@pytest.mark.parametrize(
    ("member_id", "as_of", "expected"), [(320, date(2026, 9, 24), 2), (324, date(2026, 9, 25), 0)]
)
async def test_fee_candidates_in_the_lookback(
    ro: AsyncConnection, member_id: int, as_of: date, expected: int
) -> None:
    candidates = await find_fee_candidates(ro, member_id, since=date(2026, 5, 28), until=as_of)

    assert len(candidates) == expected


async def test_fee_candidates_say_whether_a_refund_action_exists(ro: AsyncConnection) -> None:
    candidates = await find_fee_candidates(ro, ANA, since=date(2026, 5, 18), until=ANA_AS_OF)

    assert [(c.transaction.id, c.has_refund_action) for c in candidates] == [(88002, False)]


@pytest.mark.parametrize(
    ("member_id", "flags"),
    [
        (316, [("PAST_FRAUD", True)]),
        (317, [("DEBT_IN_COLLECTIONS", False)]),
        (318, [("DEBT_IN_COLLECTIONS", True)]),
        (ANA, []),
    ],
)
async def test_member_standing_lists_flags_with_resolution(
    ro: AsyncConnection, member_id: int, flags: list[tuple[str, bool]]
) -> None:
    standing = await get_member_standing(ro, member_id)

    assert [(f.flag, f.resolved_at is not None) for f in standing.flags] == flags


async def test_search_policy_finds_the_refund_limit_passage(ro: AsyncConnection) -> None:
    hits = await search_policy(ro, "refund limit per member 12 months")

    assert hits[0].document_title == "Fee Refund Policy"
    assert hits[0].text.startswith("Members in good standing may receive up to 3 fee refunds")
    assert len(hits) <= 5


async def test_recorder_times_each_tool_call(ro: AsyncConnection) -> None:
    recorder = ToolRecorder()

    standing = await recorder.run("get_member_standing", get_member_standing(ro, 316))

    assert standing.flags
    assert [(c.name, c.ok) for c in recorder.calls] == [("get_member_standing", True)]
    assert recorder.calls[0].latency_ms >= 0
