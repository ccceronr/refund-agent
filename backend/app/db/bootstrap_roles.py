"""Creates or updates the `app_rw` and `agent_ro` roles (design §3.3, R-31).

Runs before migrations (compose `migrate`, Railway pre-deploy command) and is the only
code that uses DATABASE_ADMIN_URL. Idempotent, and all-or-nothing (one transaction).
Table grants for `agent_ro` come with the migrations, not from here.

Usage: python -m app.db.bootstrap_roles
"""

import asyncio
import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field

import asyncpg
import structlog
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from app.core.logging import configure_logging

STATEMENT_TIMEOUT = "5s"  # design §3.3
SCRAM_ITERATIONS = 4096  # Postgres' own default (scram_iterations)
SCRAM_SALT_BYTES = 16

# DDL cannot take bind parameters, so Postgres builds each statement with
# format(%I, %L) from bound values: we never quote identifiers or values ourselves.
# Passwords go in as SCRAM verifiers, never as plain text (see scram_sha256_verifier).
CREATE_ROLE = "CREATE ROLE %I LOGIN PASSWORD %L"
ALTER_ROLE = "ALTER ROLE %I LOGIN PASSWORD %L"
SET_STATEMENT_TIMEOUT = "ALTER ROLE %I SET statement_timeout = %L"
GRANT_CONNECT = "GRANT CONNECT ON DATABASE %I TO %I, %I"
# R-31: agent_ro reads and nothing else, so no temporary tables for anyone by default.
REVOKE_PUBLIC_TEMPORARY = "REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC"
GIVE_SCHEMA_TO_OWNER = "ALTER SCHEMA public OWNER TO %I"
GRANT_SCHEMA_USAGE = "GRANT USAGE ON SCHEMA public TO %I"

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RoleNames:
    app_rw: str
    agent_ro: str


# The roles the app uses. Tests pass throwaway names: roles are cluster-wide.
APP_ROLES = RoleNames(app_rw="app_rw", agent_ro="agent_ro")


@dataclass(frozen=True)
class RolePasswords:
    app_rw: str = field(repr=False)
    agent_ro: str = field(repr=False)


class BootstrapSettings(BaseSettings):
    model_config = SettingsConfigDict(env_ignore_empty=True, hide_input_in_errors=True)

    database_admin_url: SecretStr
    app_rw_password: SecretStr
    agent_ro_password: SecretStr


async def bootstrap_roles(
    admin_url: str, passwords: RolePasswords, names: RoleNames = APP_ROLES
) -> None:
    _require_passwords(passwords)
    connection = await asyncpg.connect(_asyncpg_dsn(admin_url))
    try:
        async with connection.transaction():
            await _upsert_login_role(connection, names.app_rw, passwords.app_rw)
            await _upsert_login_role(connection, names.agent_ro, passwords.agent_ro)
            await _grant_baseline(connection, names)
    finally:
        await connection.close()


def scram_sha256_verifier(password: str, salt: bytes, iterations: int = SCRAM_ITERATIONS) -> str:
    """The value Postgres stores for a SCRAM-SHA-256 password (RFC 5802, RFC 7677).

    Sending this instead of the password keeps the password out of the server logs:
    Postgres logs the full text of a failing statement by default (psql's \\password
    does the same).
    """
    salted = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    stored_key = hashlib.sha256(hmac.digest(salted, b"Client Key", "sha256")).digest()
    server_key = hmac.digest(salted, b"Server Key", "sha256")
    return f"SCRAM-SHA-256${iterations}:{_b64(salt)}${_b64(stored_key)}:{_b64(server_key)}"


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _require_passwords(passwords: RolePasswords) -> None:
    for password in (passwords.app_rw, passwords.agent_ro):
        # OWASP A02: no default or empty passwords, ever.
        if not password:
            raise ValueError("APP_RW_PASSWORD and AGENT_RO_PASSWORD must not be empty passwords")
        # Postgres normalizes non-ASCII passwords (SASLprep) before hashing; we only hash,
        # so keep to the range where that normalization changes nothing.
        if not (password.isascii() and password.isprintable()):
            raise ValueError("Role passwords must be printable ASCII, e.g. secrets.token_urlsafe")


def _asyncpg_dsn(url: str) -> str:
    # Accept both `postgresql://` and SQLAlchemy's `postgresql+asyncpg://` forms.
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


async def _upsert_login_role(connection: asyncpg.Connection, role: str, password: str) -> None:
    exists = await connection.fetchval(
        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $1)", role
    )
    verifier = scram_sha256_verifier(password, secrets.token_bytes(SCRAM_SALT_BYTES))
    await _execute(connection, ALTER_ROLE if exists else CREATE_ROLE, role, verifier)
    await _execute(connection, SET_STATEMENT_TIMEOUT, role, STATEMENT_TIMEOUT)


async def _grant_baseline(connection: asyncpg.Connection, names: RoleNames) -> None:
    database = await connection.fetchval("SELECT current_database()")
    await _execute(connection, GRANT_CONNECT, database, names.app_rw, names.agent_ro)
    await _execute(connection, REVOKE_PUBLIC_TEMPORARY, database)
    await _execute(connection, GIVE_SCHEMA_TO_OWNER, names.app_rw)
    await _execute(connection, GRANT_SCHEMA_USAGE, names.agent_ro)


async def _execute(connection: asyncpg.Connection, template: str, *values: str) -> None:
    statement = await connection.fetchval(
        "SELECT format($1, VARIADIC $2::text[])", template, list(values)
    )
    await connection.execute(statement)


async def _main() -> None:
    configure_logging()
    settings = BootstrapSettings()
    passwords = RolePasswords(
        app_rw=settings.app_rw_password.get_secret_value(),
        agent_ro=settings.agent_ro_password.get_secret_value(),
    )
    await bootstrap_roles(settings.database_admin_url.get_secret_value(), passwords)
    log.info("roles_bootstrapped", roles=[APP_ROLES.app_rw, APP_ROLES.agent_ro])


if __name__ == "__main__":
    asyncio.run(_main())
