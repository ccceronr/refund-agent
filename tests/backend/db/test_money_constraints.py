"""Money integrity enforced by the database itself, whatever the code does (R-15, BR-05, BR-11)."""

import uuid

import asyncpg
import pytest

REFUND = (
    "INSERT INTO refund_actions (case_id, fee_transaction_id, refund_transaction_id, amount,"
    " actor_id) VALUES ($1, $2, 88003, $3, 'S14')"
)
DECISION = (
    "INSERT INTO decisions (case_id, actor_id, action, outcome, idempotency_key)"
    " VALUES ($1, 'S14', 'reject', 'none', $2)"
)


@pytest.fixture
async def rolled_back(seeded_db: dict[str, str], connect_as) -> asyncpg.Connection:
    async with connect_as("app_rw") as connection:
        transaction = connection.transaction()
        await transaction.start()
        try:
            yield connection
        finally:
            await transaction.rollback()


async def test_a_fee_can_be_refunded_only_once(rolled_back: asyncpg.Connection) -> None:
    await rolled_back.execute(REFUND, 5012, 88002, 35)

    with pytest.raises(asyncpg.UniqueViolationError):
        await rolled_back.execute(REFUND, 5013, 88002, 35)


async def test_a_case_gets_at_most_one_refund(rolled_back: asyncpg.Connection) -> None:
    await rolled_back.execute(REFUND, 5012, 88002, 35)

    with pytest.raises(asyncpg.UniqueViolationError):
        await rolled_back.execute(REFUND, 5012, 89003, 35)


@pytest.mark.parametrize("amount", [0, -35])
async def test_a_refund_amount_must_be_positive(
    rolled_back: asyncpg.Connection, amount: int
) -> None:
    with pytest.raises(asyncpg.CheckViolationError):
        await rolled_back.execute(REFUND, 5012, 88002, amount)


async def test_an_idempotency_key_is_one_decision_per_case(
    rolled_back: asyncpg.Connection,
) -> None:
    key = uuid.uuid4()
    await rolled_back.execute(DECISION, 5012, key)

    with pytest.raises(asyncpg.UniqueViolationError):
        await rolled_back.execute(DECISION, 5012, key)
