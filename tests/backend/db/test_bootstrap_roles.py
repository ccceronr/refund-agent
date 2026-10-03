"""Roles bootstrap: both roles exist, can log in, stay least-privilege (design §3.3, R-31).

Roles are cluster-wide, so these tests never touch the real app_rw/agent_ro: each test
bootstraps throwaway roles with their own names into a throwaway database (the bootstrap
takes ownership of the schema), and drops both afterwards.
"""

import base64
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import asyncpg
import pytest
from sqlalchemy.engine import make_url

from app.db.bootstrap_roles import (
    RoleNames,
    RolePasswords,
    bootstrap_roles,
    scram_sha256_verifier,
)

TRICKY = RolePasswords(app_rw="it's 100% $ecret \\o/", agent_ro='say "hi"; DROP ROLE x; --')


@dataclass(frozen=True)
class Scratch:
    url: str
    names: RoleNames
    passwords: RolePasswords


@asynccontextmanager
async def _as_admin(url: str) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(url)
    try:
        yield connection
    finally:
        await connection.close()


async def _run(admin: asyncpg.Connection, template: str, *values: str) -> None:
    statement = await admin.fetchval("SELECT format($1, VARIADIC $2::text[])", template, values)
    await admin.execute(statement)


@pytest.fixture
async def scratch(admin_url: str) -> AsyncIterator[Scratch]:
    suffix = secrets.token_hex(4)
    names = RoleNames(app_rw=f"probe_rw_{suffix}", agent_ro=f"probe_ro_{suffix}")
    passwords = RolePasswords(app_rw=secrets.token_urlsafe(16), agent_ro=secrets.token_urlsafe(16))
    database = f"bootstrap_probe_{suffix}"
    async with _as_admin(admin_url) as admin:
        await _run(admin, "CREATE DATABASE %I", database)
    url = make_url(admin_url).set(database=database).render_as_string(hide_password=False)
    try:
        yield Scratch(url=url, names=names, passwords=passwords)
    finally:
        async with _as_admin(admin_url) as admin:
            await _run(admin, "DROP DATABASE IF EXISTS %I WITH (FORCE)", database)
            await _run(admin, "DROP ROLE IF EXISTS %I, %I", names.app_rw, names.agent_ro)


@asynccontextmanager
async def _login(scratch: Scratch, role: str, password: str) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(scratch.url, user=role, password=password)
    try:
        yield connection
    finally:
        await connection.close()


async def _can_log_in(scratch: Scratch, role: str, password: str) -> bool:
    try:
        async with _login(scratch, role, password):
            return True
    except asyncpg.InvalidPasswordError:
        return False


async def _bootstrap(scratch: Scratch, passwords: RolePasswords | None = None) -> None:
    await bootstrap_roles(scratch.url, passwords or scratch.passwords, scratch.names)


async def test_both_roles_can_log_in_after_the_bootstrap(scratch: Scratch) -> None:
    await _bootstrap(scratch)

    assert await _can_log_in(scratch, scratch.names.app_rw, scratch.passwords.app_rw)
    assert await _can_log_in(scratch, scratch.names.agent_ro, scratch.passwords.agent_ro)


async def test_both_roles_get_a_5_second_statement_timeout(scratch: Scratch) -> None:
    await _bootstrap(scratch)

    for role, password in (
        (scratch.names.app_rw, scratch.passwords.app_rw),
        (scratch.names.agent_ro, scratch.passwords.agent_ro),
    ):
        async with _login(scratch, role, password) as connection:
            assert await connection.fetchval("SHOW statement_timeout") == "5s"


async def test_running_the_bootstrap_again_restores_a_changed_password(scratch: Scratch) -> None:
    await _bootstrap(scratch)
    async with _as_admin(scratch.url) as admin:
        await _run(admin, "ALTER ROLE %I PASSWORD %L", scratch.names.app_rw, "changed-elsewhere")

    await _bootstrap(scratch)

    assert await _can_log_in(scratch, scratch.names.app_rw, scratch.passwords.app_rw)


async def test_passwords_with_quotes_and_symbols_work(scratch: Scratch) -> None:
    await _bootstrap(scratch, TRICKY)

    assert await _can_log_in(scratch, scratch.names.app_rw, TRICKY.app_rw)
    assert await _can_log_in(scratch, scratch.names.agent_ro, TRICKY.agent_ro)


async def test_app_rw_owns_the_schema_so_it_can_run_migrations(scratch: Scratch) -> None:
    await _bootstrap(scratch)

    async with _login(scratch, scratch.names.app_rw, scratch.passwords.app_rw) as connection:
        await connection.execute("CREATE TABLE migration_probe (id int)")


async def test_agent_ro_cannot_create_tables(scratch: Scratch) -> None:
    await _bootstrap(scratch)

    async with _login(scratch, scratch.names.agent_ro, scratch.passwords.agent_ro) as connection:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute("CREATE TABLE probe (id int)")


async def test_agent_ro_cannot_create_temporary_tables(scratch: Scratch) -> None:
    await _bootstrap(scratch)

    async with _login(scratch, scratch.names.agent_ro, scratch.passwords.agent_ro) as connection:
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await connection.execute("CREATE TEMPORARY TABLE probe (id int)")


async def test_scram_verifier_is_exactly_what_postgres_stores(admin_url: str) -> None:
    # Postgres itself is the oracle: let it hash a password, then rebuild that hash.
    role = f"scram_probe_{secrets.token_hex(4)}"
    async with _as_admin(admin_url) as admin:
        await admin.execute("SET password_encryption = 'scram-sha-256'")
        await _run(admin, "CREATE ROLE %I PASSWORD %L", role, TRICKY.app_rw)
        try:
            stored = await admin.fetchval(
                "SELECT rolpassword FROM pg_authid WHERE rolname = $1", role
            )
        finally:
            await _run(admin, "DROP ROLE %I", role)
    iterations, salt = stored.split("$")[1].split(":")

    verifier = scram_sha256_verifier(TRICKY.app_rw, base64.b64decode(salt), int(iterations))

    assert verifier == stored


@pytest.mark.parametrize(
    "passwords",
    [RolePasswords(app_rw="", agent_ro="x"), RolePasswords(app_rw="x", agent_ro="")],
)
async def test_bootstrap_refuses_empty_passwords(passwords: RolePasswords) -> None:
    with pytest.raises(ValueError, match="password"):
        await bootstrap_roles("postgresql://postgres:unused@127.0.0.1:1/refunds", passwords)


async def test_bootstrap_refuses_non_ascii_passwords() -> None:
    passwords = RolePasswords(app_rw="contraseña", agent_ro="x")

    with pytest.raises(ValueError, match="ASCII"):
        await bootstrap_roles("postgresql://postgres:unused@127.0.0.1:1/refunds", passwords)
