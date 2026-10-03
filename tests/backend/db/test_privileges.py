"""agent_ro reads only what the agent tools need and never writes (design §3.3, R-31).

audit_log is append-only even for app_rw (R-35, OWASP A09).
"""

import asyncpg
import pytest

READABLE_BY_AGENT = [
    "conversations",
    "messages",
    "accounts",
    "sub_accounts",
    "transactions",
    "credit_unions",
    "member_profiles",
    "member_flags",
    "refund_actions",
    "policy_documents",
    "policy_passages",
]
HIDDEN_FROM_AGENT = [
    "staff",
    "cases",
    "agent_runs",
    "agent_steps",
    "proposals",
    "decisions",
    "audit_log",
    "feedback_evals",
]
AGENT_WRITES = [
    "INSERT INTO messages (id, conversation_id, author_id, body, created_at)"
    " VALUES (99999, 5012, '301', 'x', now())",
    "UPDATE transactions SET amount = 0 WHERE id = 88002",
    "DELETE FROM refund_actions",
    "INSERT INTO policy_passages (document_id, ordinal, text) VALUES (1, 99, 'x')",
]


async def _count(connection: asyncpg.Connection, table: str) -> int:
    statement = await connection.fetchval(
        "SELECT format('SELECT count(*) FROM %I', $1::text)", table
    )
    count: int = await connection.fetchval(statement)
    return count


@pytest.mark.parametrize("table", READABLE_BY_AGENT)
async def test_agent_ro_can_read_the_tables_the_tools_need(
    seeded_db: dict[str, str], connect_as, table: str
) -> None:
    async with connect_as("agent_ro") as connection:
        assert await _count(connection, table) >= 0


@pytest.mark.parametrize("table", HIDDEN_FROM_AGENT)
async def test_agent_ro_cannot_read_app_state_or_staff(
    seeded_db: dict[str, str], connect_as, table: str
) -> None:
    async with connect_as("agent_ro") as connection:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await _count(connection, table)


@pytest.mark.parametrize("statement", AGENT_WRITES)
async def test_agent_ro_cannot_write(seeded_db: dict[str, str], connect_as, statement: str) -> None:
    async with connect_as("agent_ro") as connection:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute(statement)


@pytest.mark.parametrize(
    "change",
    ["UPDATE audit_log SET event = 'edited'", "DELETE FROM audit_log"],
)
async def test_audit_log_rows_can_never_be_changed_or_deleted(
    seeded_db: dict[str, str], connect_as, change: str
) -> None:
    async with connect_as("app_rw") as connection:
        transaction = connection.transaction()
        await transaction.start()
        try:
            await connection.execute(
                "INSERT INTO audit_log (actor_id, event, details) VALUES ('S14', 'probe', '{}')"
            )
            with pytest.raises(asyncpg.RaiseError, match="append-only"):
                await connection.execute(change)
        finally:
            await transaction.rollback()
