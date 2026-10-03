"""`python -m seed.seed` behaviour: safe to re-run, reset for demos, never resets production.

Runs the real CLI as a subprocess against the test database (seed-and-evals §1, tasks P1).
"""

import asyncpg
import pytest

PRODUCTION_ENV = {
    "APP_ENV": "production",
    "DATABASE_URL_RO": "postgresql+asyncpg://agent_ro:unused@127.0.0.1:1/refunds",
    "ANTHROPIC_API_KEY": "test-key",
    "JEV_API_KEY": "test-key",
    "SESSION_SECRET": "s" * 48,
}
SNAPSHOT = """
    SELECT md5(string_agg(t::text, '|' ORDER BY t.id)) FROM transactions t
"""


@pytest.fixture
async def db(seeded_db: dict[str, str], connect_as) -> asyncpg.Connection:
    async with connect_as("app_rw") as connection:
        yield connection


async def test_if_empty_leaves_a_seeded_database_untouched(
    seeded_db: dict[str, str], db: asyncpg.Connection, backend_cli
) -> None:
    await db.execute(
        "INSERT INTO audit_log (actor_id, event, details) VALUES ('S14', 'kept', '{}')"
    )
    try:
        result = backend_cli(seeded_db, "-m", "seed.seed", "--if-empty")

        assert result.returncode == 0, result.stderr
        assert await db.fetchval("SELECT count(*) FROM audit_log WHERE event = 'kept'") == 1
    finally:
        backend_cli(seeded_db, "-m", "seed.seed", "--reset")


async def test_reset_rebuilds_the_same_data_and_clears_demo_state(
    seeded_db: dict[str, str], db: asyncpg.Connection, backend_cli
) -> None:
    before = await db.fetchval(SNAPSHOT)
    await db.execute(
        "INSERT INTO audit_log (actor_id, event, details) VALUES ('S14', 'demo', '{}')"
    )
    await db.execute("UPDATE cases SET status = 'resolved' WHERE conversation_id = 5012")

    result = backend_cli(seeded_db, "-m", "seed.seed", "--reset")

    assert result.returncode == 0, result.stderr
    assert await db.fetchval(SNAPSHOT) == before
    assert await db.fetchval("SELECT count(*) FROM audit_log") == 0
    assert await db.fetchval("SELECT status FROM cases WHERE conversation_id = 5012") == "new"


async def test_reset_is_refused_in_production(
    seeded_db: dict[str, str], db: asyncpg.Connection, backend_cli
) -> None:
    await db.execute("UPDATE cases SET status = 'ready' WHERE conversation_id = 5013")
    try:
        result = backend_cli({**seeded_db, **PRODUCTION_ENV}, "-m", "seed.seed", "--reset")

        assert result.returncode != 0
        assert "production" in (result.stderr + result.stdout)
        assert await db.fetchval("SELECT status FROM cases WHERE conversation_id = 5013") == "ready"
    finally:
        backend_cli(seeded_db, "-m", "seed.seed", "--reset")


def test_the_seed_needs_an_explicit_mode(seeded_db: dict[str, str], backend_cli) -> None:
    result = backend_cli(seeded_db, "-m", "seed.seed")

    assert result.returncode != 0


async def test_new_rows_get_ids_after_the_seeded_ones(db: asyncpg.Connection) -> None:
    # The app will insert replies and refund transactions without explicit ids (BR-11, BR-12).
    transaction = db.transaction()
    await transaction.start()
    try:
        message_id = await db.fetchval(
            "INSERT INTO messages (conversation_id, author_id, body, created_at)"
            " VALUES (5012, 'S14', 'reply', now()) RETURNING id"
        )
        transaction_id = await db.fetchval(
            "INSERT INTO transactions (sub_account_id, date, description, amount, balance_after,"
            " posting_ref) VALUES (1302, '2026-09-30', 'probe', 1, 1, '20260930-9999')"
            " RETURNING id"
        )
    finally:
        await transaction.rollback()

    assert message_id > await db.fetchval("SELECT max(id) FROM messages")
    assert transaction_id > await db.fetchval("SELECT max(id) FROM transactions")
