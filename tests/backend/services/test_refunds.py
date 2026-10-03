"""RefundService.execute: the only code path that moves money (BR-11, BR-05, BR-09, BR-10)."""

from collections.abc import AsyncIterator, Callable
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.db.engines import create_rw_engine
from app.rules.model import Role, Thresholds
from app.services.errors import ApprovalNotAllowed, FeeAlreadyRefunded, NoFeeIdentified
from app.services.refunds import Actor, RefundService

TODAY = date(2026, 10, 3)
LUIS = Actor("S14", Role.STAFF)
MARTA = Actor("S02", Role.SUPERVISOR)
AUTOMATIC = Actor("S00", Role.SYSTEM)


@pytest.fixture
async def rw(fresh_db: None, make_settings: Callable[..., Settings]) -> AsyncIterator[AsyncEngine]:
    engine = create_rw_engine(make_settings())
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def service() -> RefundService:
    return RefundService(
        Thresholds.from_settings(Settings(app_env="local", database_url_rw="unused")),
        today=lambda: TODAY,
    )


async def refund(
    rw: AsyncEngine, service: RefundService, case_id: int, fee_id: int, actor: Actor = LUIS
):
    async with rw.begin() as connection:
        return await service.execute(
            connection,
            case_id=case_id,
            fee_transaction_id=fee_id,
            actor=actor,
            idempotency_key="key-1",
        )


async def rows(rw: AsyncEngine, sql: str, **params: object) -> list[tuple[object, ...]]:
    async with rw.connect() as connection:
        return [tuple(r) for r in await connection.execute(text(sql), params)]


async def test_the_fee_amount_goes_back_into_the_fee_sub_account(rw, service) -> None:
    result = await refund(rw, service, 5012, 88002)

    assert result.amount == Decimal("35.00")
    assert await rows(
        rw,
        "SELECT description, amount, balance_after, date, posting_ref FROM transactions WHERE id = :id",
        id=result.refund_transaction_id,
    ) == [
        (
            "Deposit Fee Refund Courtesy Pay fee",
            Decimal("35.00"),
            Decimal("1360.00"),
            TODAY,
            "20261003-0000",
        )
    ]
    assert await rows(rw, "SELECT balance, available FROM sub_accounts WHERE id = 1302") == [
        (Decimal("1360.00"), Decimal("1360.00"))
    ]


async def test_the_refund_is_recorded_and_audited(rw, service) -> None:
    result = await refund(rw, service, 5012, 88002)

    assert await rows(
        rw,
        "SELECT case_id, fee_transaction_id, refund_transaction_id, amount, actor_id FROM refund_actions",
    ) == [(5012, 88002, result.refund_transaction_id, Decimal("35.00"), "S14")]
    [(event, actor, case_id, details)] = await rows(
        rw, "SELECT event, actor_id, case_id, details FROM audit_log"
    )
    assert (event, actor, case_id) == ("refund_executed", "S14", 5012)
    assert details["amount"] == "35.00"
    assert details["fee_transaction_id"] == 88002


async def test_a_fee_is_never_refunded_twice(rw, service) -> None:
    await refund(rw, service, 5012, 88002)

    with pytest.raises(FeeAlreadyRefunded):
        await refund(rw, service, 5012, 88002, MARTA)

    assert await rows(
        rw, "SELECT count(*) FROM transactions WHERE sub_account_id = 1302 AND date = :d", d=TODAY
    ) == [(1,)]


async def test_a_fee_refunded_by_a_matching_ledger_entry_is_refused(rw, service) -> None:
    ava_fee = (
        await rows(
            rw,
            "SELECT t.id FROM transactions t JOIN sub_accounts s ON s.id = t.sub_account_id JOIN accounts a ON a.id = s.account_id WHERE a.member_id = 323 AND t.amount < 0 AND t.description LIKE 'Fee Withdrawal%'",
        )
    )[0][0]

    with pytest.raises(FeeAlreadyRefunded):
        await refund(rw, service, 5026, ava_fee, MARTA)


async def olivia_fee(rw: AsyncEngine) -> int:
    return (
        await rows(
            rw,
            "SELECT t.id FROM transactions t JOIN sub_accounts s ON s.id = t.sub_account_id JOIN accounts a ON a.id = s.account_id WHERE a.member_id = 312 AND t.description LIKE 'Fee Withdrawal%'",
        )
    )[0][0]


@pytest.mark.parametrize("actor", [LUIS, AUTOMATIC], ids=["staff", "automatic-flow"])
async def test_a_policy_exception_needs_a_supervisor(rw, service, actor: Actor) -> None:
    with pytest.raises(ApprovalNotAllowed) as refused:
        await refund(rw, service, 5015, await olivia_fee(rw), actor)

    assert (
        refused.value.message
        == "This refund needs a supervisor's approval because Olivia has already used every refund available this year."
    )
    assert await rows(rw, "SELECT count(*) FROM refund_actions") == [(0,)]


async def test_a_supervisor_can_make_the_policy_exception(rw, service) -> None:
    result = await refund(rw, service, 5015, await olivia_fee(rw), MARTA)

    assert result.amount == Decimal("35.00")


async def test_a_fee_of_another_member_cannot_be_refunded_on_this_case(rw, service) -> None:
    with pytest.raises(NoFeeIdentified):
        await refund(rw, service, 5013, 88002)

    assert await rows(rw, "SELECT count(*) FROM refund_actions") == [(0,)]


async def test_a_transaction_that_is_not_a_fee_cannot_be_refunded(rw, service) -> None:
    with pytest.raises(NoFeeIdentified):
        await refund(rw, service, 5012, 88003)  # Ana's payroll deposit
