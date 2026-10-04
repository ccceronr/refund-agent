"""Loads the demo data: PDF rows, scenarios, policies, staff, profiles and cases.

Usage (from backend/, as app_rw via DATABASE_URL_RW):
  python -m seed.seed --if-empty   # compose `migrate` and Railway pre-deploy: never
                                   # touches a database that already has data
  python -m seed.seed --reset      # local demo rehearsal: wipe everything and reload;
                                   # refused when APP_ENV=production

Everything happens in one transaction (seed-and-evals §1).
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Table, func, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.passwords import hash_password
from app.db.engines import create_rw_engine
from app.db.models import (
    Account,
    Base,
    Case,
    Conversation,
    CreditUnion,
    MemberFlag,
    MemberProfile,
    Message,
    PolicyDocument,
    PolicyPassage,
    Staff,
    SubAccount,
    Transaction,
)
from seed import pdf_rows
from seed.ledger import LedgerRow, closing_balance, post_days
from seed.scenarios import CREDIT_UNION_ID, SCENARIOS, TOM_SAVINGS_FEE_DAY, Scenario

FIRST_ACCOUNT_ID = 800
FIRST_SUB_ACCOUNT_ID = 1400
FIRST_TRANSACTION_ID = 89000
FIRST_MESSAGE_ID = 9121
FIRST_ACCOUNT_NUMBER = 885001
TOM_SAVINGS_SUB_ACCOUNT_ID = 1255
CLOSED_PDF_CONVERSATION_ID = 5009
POLICIES_DIR = Path(__file__).parent / "policies"
# Same order as specs/policies.md, so document ids read like the spec.
POLICY_SLUGS = (
    "fee-refund-policy",
    "fee-schedule",
    "overdraft-program",
    "posting-order",
    "good-standing",
    "approval-authority",
    "member-communication",
)

CREDIT_UNIONS: list[dict[str, Any]] = [
    {"id": 7, "name": "Riverbend Credit Union"},
    {"id": 9, "name": "Lakeside Community Credit Union"},
]
# Password hashes for luis and marta come from the environment (design §4.0).
STAFF: list[dict[str, Any]] = [
    {"id": "S00", "first_name": "Automatic refunds", "role": "system", "username": None},
    {"id": "S02", "first_name": "Marta", "role": "supervisor", "username": "marta"},
    {"id": "S14", "first_name": "Luis", "role": "staff", "username": "luis"},
]
# TRUNCATE has no SQLAlchemy construct; this is a constant, checked by _assert_all_empty.
TRUNCATE_ALL = text(
    "TRUNCATE TABLE audit_log, feedback_evals, refund_actions, decisions, proposals,"
    " agent_steps, agent_runs, cases, policy_passages, policy_documents, staff,"
    " member_flags, member_profiles, transactions, sub_accounts, accounts, messages,"
    " conversations, credit_unions RESTART IDENTITY CASCADE"
)

log = structlog.get_logger(__name__)


class SeedRefused(RuntimeError):
    pass


class StaffPasswords(BaseSettings):
    """Sign-in passwords for the seeded staff users, read only by the seed (design §4.0)."""

    model_config = SettingsConfigDict(env_ignore_empty=True, hide_input_in_errors=True)

    seed_password_luis: SecretStr | None = None
    seed_password_marta: SecretStr | None = None

    def by_username(self) -> dict[str, SecretStr | None]:
        return {"luis": self.seed_password_luis, "marta": self.seed_password_marta}


async def run_seed(settings: Settings, passwords: StaffPasswords, *, reset: bool) -> None:
    if reset and settings.is_production:
        # OWASP A08: a redeploy or a typo must never wipe production decisions.
        raise SeedRefused("--reset is refused when APP_ENV=production")
    missing = [
        f"SEED_PASSWORD_{name.upper()}" for name, v in passwords.by_username().items() if not v
    ]
    if missing and settings.is_production:
        # OWASP A02: no default or missing passwords in production.
        raise SeedRefused(f"{', '.join(missing)} must be set in production")
    engine = create_rw_engine(settings)
    try:
        async with engine.begin() as connection:
            await _seed(connection, reset=reset)
            await _set_staff_passwords(connection, passwords)
    finally:
        await engine.dispose()


async def _set_staff_passwords(connection: AsyncConnection, passwords: StaffPasswords) -> None:
    # Runs on every deploy (also with --if-empty), so changing a variable rotates a password.
    for username, password in passwords.by_username().items():
        if password is None:
            # Local only (production refuses above): the stored hash, if any, is kept.
            log.warning("staff_password_not_set", username=username, effect="hash unchanged")
            continue
        await connection.execute(
            update(Staff)
            .where(Staff.username == username)
            .values(password_hash=hash_password(password.get_secret_value()))
        )


async def _seed(connection: AsyncConnection, *, reset: bool) -> None:
    if reset:
        await connection.execute(TRUNCATE_ALL)
        await _assert_all_empty(connection)
    elif await _has_data(connection):
        log.info("seed_skipped", reason="database already has data")
        return
    await _insert_everything(connection)
    await _advance_id_sequences(connection)
    log.info("seed_loaded", conversations=len(pdf_rows.CONVERSATIONS) + len(SCENARIOS))


async def _has_data(connection: AsyncConnection) -> bool:
    count = await connection.scalar(select(func.count()).select_from(Conversation))
    return bool(count)


async def _assert_all_empty(connection: AsyncConnection) -> None:
    for table in Base.metadata.sorted_tables:
        if await connection.scalar(select(func.count()).select_from(table)):
            raise RuntimeError(f"--reset left rows in {table.name}; update TRUNCATE_ALL")


async def _insert_everything(connection: AsyncConnection) -> None:
    rows = _all_rows()
    for model in (
        CreditUnion, Staff, MemberProfile, MemberFlag, Conversation, Message,
        Account, SubAccount, Transaction, Case,
    ):  # fmt: skip
        table: Table = model.__table__  # type: ignore[assignment]  # mapped classes have a Table
        # An empty list would run one INSERT with no values, not zero INSERTs.
        if rows[model.__tablename__]:
            await connection.execute(insert(table), rows[model.__tablename__])
    await _insert_policies(connection)


def _all_rows() -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {
        "credit_unions": CREDIT_UNIONS,
        "staff": STAFF,
        "member_profiles": list(pdf_rows.PROFILES),
        "member_flags": [],
        "conversations": list(pdf_rows.CONVERSATIONS),
        "messages": list(pdf_rows.MESSAGES),
        "accounts": list(pdf_rows.ACCOUNTS),
        "sub_accounts": list(pdf_rows.SUB_ACCOUNTS),
        "transactions": list(pdf_rows.TRANSACTIONS),
    }
    next_transaction_id = _add_tom_savings_fee(rows, FIRST_TRANSACTION_ID)
    for index, scenario in enumerate(SCENARIOS):
        next_transaction_id = _add_scenario(rows, index, scenario, next_transaction_id)
    seeded_at = datetime.now(UTC)
    rows["cases"] = [_case_for(conversation, seeded_at) for conversation in rows["conversations"]]
    return rows


def _add_tom_savings_fee(rows: dict[str, list[dict[str, Any]]], next_id: int) -> int:
    ledger = post_days((TOM_SAVINGS_FEE_DAY,))
    return _add_transactions(rows, TOM_SAVINGS_SUB_ACCOUNT_ID, ledger, next_id)


def _add_scenario(
    rows: dict[str, list[dict[str, Any]]], index: int, scenario: Scenario, next_id: int
) -> int:
    account_id = FIRST_ACCOUNT_ID + index
    sub_account_id = FIRST_SUB_ACCOUNT_ID + index
    ledger = post_days(scenario.days)
    balance = closing_balance(ledger)
    rows["member_profiles"].append(
        {
            "member_id": scenario.member_id,
            "first_name": scenario.first_name,
            "last_name": scenario.last_name,
        }
    )
    rows["member_flags"] += [
        {
            "member_id": scenario.member_id,
            "flag": flag.flag,
            "created_at": _midnight_utc(flag.created),
            "resolved_at": _midnight_utc(flag.resolved) if flag.resolved else None,
        }
        for flag in scenario.flags
    ]
    rows["conversations"].append(
        {
            "id": scenario.conversation_id,
            "member_id": scenario.member_id,
            "subject": scenario.subject,
            "status": "waiting_for_bank",
            "created_at": scenario.sent_at,
        }
    )
    rows["messages"].append(
        {
            "id": FIRST_MESSAGE_ID + index,
            "conversation_id": scenario.conversation_id,
            "author_id": str(scenario.member_id),
            "body": scenario.message,
            "created_at": scenario.sent_at,
        }
    )
    rows["accounts"].append(
        {
            "id": account_id,
            "member_id": scenario.member_id,
            "credit_union_id": CREDIT_UNION_ID,
            "account_number": str(FIRST_ACCOUNT_NUMBER + index),
            "is_primary": True,
        }
    )
    rows["sub_accounts"].append(
        {
            "id": sub_account_id,
            "account_id": account_id,
            "type": "CHECKING",
            "name": "Everyday Checking",
            "balance": balance,
            "available": balance,
        }
    )
    return _add_transactions(rows, sub_account_id, ledger, next_id)  # fmt: skip


def _add_transactions(
    rows: dict[str, list[dict[str, Any]]],
    sub_account_id: int,
    ledger: list[LedgerRow],
    next_id: int,
) -> int:
    for offset, row in enumerate(ledger):
        rows["transactions"].append(
            {"id": next_id + offset, "sub_account_id": sub_account_id, "date": row.date,
             "description": row.description, "amount": row.amount,
             "balance_after": row.balance_after, "posting_ref": row.posting_ref}
        )  # fmt: skip
    return next_id + len(ledger)


def _case_for(conversation: dict[str, Any], seeded_at: datetime) -> dict[str, Any]:
    # Every row has the same keys: a multi-row INSERT takes its columns from the first row
    # and would silently drop the others' extra values.
    if conversation["id"] == CLOSED_PDF_CONVERSATION_ID:
        # Closed in August: resolved, and old enough to stay out of "Done today" (R-01).
        closed_at = conversation["created_at"].replace(tzinfo=UTC)
        return {"conversation_id": conversation["id"], "status": "resolved", "category": "other",
                "created_at": closed_at, "updated_at": closed_at}  # fmt: skip
    return {"conversation_id": conversation["id"], "status": "new", "category": "unknown",
            "created_at": seeded_at, "updated_at": seeded_at}  # fmt: skip


def _midnight_utc(day: Any) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


async def _insert_policies(connection: AsyncConnection) -> None:
    for slug in POLICY_SLUGS:
        path = POLICIES_DIR / f"{slug}.md"
        title, passages = _read_policy(path)
        document_id = await connection.scalar(
            insert(PolicyDocument)
            .values(slug=path.stem, title=title, body="\n".join(passages))
            .returning(PolicyDocument.id)
        )
        await connection.execute(
            insert(PolicyPassage),
            [
                {"document_id": document_id, "ordinal": n, "text": t}
                for n, t in enumerate(passages, 1)
            ],
        )


def _read_policy(path: Path) -> tuple[str, list[str]]:
    """One passage per bullet (policies.md): passages are quoted verbatim in the UI."""
    lines = path.read_text().splitlines()
    title = lines[0].removeprefix("# ").strip()
    passages = [line.removeprefix("- ").strip() for line in lines if line.startswith("- ")]
    return title, passages


async def _advance_id_sequences(connection: AsyncConnection) -> None:
    # Rows were inserted with explicit ids; new rows (replies, refunds) must come after.
    for table in Base.metadata.sorted_tables:
        id_column = table.c.get("id")
        if (
            id_column is None
            or not id_column.autoincrement
            or id_column.type.python_type is not int
        ):
            continue
        next_id = select(func.coalesce(func.max(id_column), 0) + 1).scalar_subquery()
        sequence = func.pg_get_serial_sequence(table.name, "id")
        await connection.execute(select(func.setval(sequence, next_id, False)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m seed.seed", description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--if-empty", action="store_true", help="seed only an empty database")
    mode.add_argument("--reset", action="store_true", help="wipe and reload (never in production)")
    args = parser.parse_args(argv)
    configure_logging()
    try:
        asyncio.run(run_seed(Settings(), StaffPasswords(), reset=args.reset))
    except SeedRefused as refused:
        log.error("seed_refused", reason=str(refused))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
