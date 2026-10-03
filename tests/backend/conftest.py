"""Shared fixtures: a disposable test database with bootstrapped roles, and app clients.

Needs a Postgres superuser URL for a database used only by tests
(`TEST_DATABASE_ADMIN_URL`) plus the role passwords (`APP_RW_PASSWORD`,
`AGENT_RO_PASSWORD`). `make test` and CI set them.
"""

import asyncio
import io
import logging
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url

from app.core.config import Settings
from app.core.logging import HANDLER_NAME, configure_logging
from app.db.bootstrap_roles import RolePasswords, bootstrap_roles
from app.main import create_app

PRODUCTION_SECRETS: dict[str, Any] = {
    "database_url_ro": "postgresql+asyncpg://agent_ro:unused@127.0.0.1:1/refunds",
    "anthropic_api_key": "test-anthropic-key",
    "jev_api_key": "test-jev-key",
    "session_secret": "s" * 48,
}

Serve = Callable[..., AbstractAsyncContextManager[AsyncClient]]


def _required_env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        pytest.exit(f"{name} must be set to run the backend tests (see Makefile or CI).", 2)
    return value


def role_url(admin_url: str, role: str, password: str, driver: str) -> str:
    """Same server and database as the admin URL, logged in as another role."""
    url = make_url(admin_url).set(drivername=driver, username=role, password=password)
    return url.render_as_string(hide_password=False)


async def _create_database_if_missing(admin_url: str) -> None:
    url = make_url(admin_url)
    maintenance = url.set(drivername="postgresql", database="postgres")
    connection = await asyncpg.connect(maintenance.render_as_string(hide_password=False))
    try:
        exists = await connection.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", url.database
        )
        if not exists:
            statement = await connection.fetchval(
                "SELECT format('CREATE DATABASE %I', $1::text)", url.database
            )
            await connection.execute(statement)
    finally:
        await connection.close()


@pytest.fixture(scope="session", autouse=True)
def json_logging() -> None:
    configure_logging()


@pytest.fixture
def log_output() -> Iterator[io.StringIO]:
    """The JSON lines our log handler writes, captured for assertions."""
    configure_logging()
    handler = next(h for h in logging.getLogger().handlers if h.name == HANDLER_NAME)
    assert isinstance(handler, logging.StreamHandler)
    stream = io.StringIO()
    previous = handler.setStream(stream)
    try:
        yield stream
    finally:
        handler.setStream(previous)


@pytest.fixture(autouse=True)
def isolated_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings read the environment; a developer's .env must not change test outcomes."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


@pytest.fixture(scope="session")
def role_passwords() -> RolePasswords:
    return RolePasswords(
        app_rw=_required_env("APP_RW_PASSWORD"),
        agent_ro=_required_env("AGENT_RO_PASSWORD"),
    )


@pytest.fixture(scope="session")
def admin_url(role_passwords: RolePasswords) -> str:
    """Superuser URL of the test database, with the roles already bootstrapped."""
    url = _required_env("TEST_DATABASE_ADMIN_URL")
    asyncio.run(_create_database_if_missing(url))
    asyncio.run(bootstrap_roles(url, role_passwords))
    return url


ConnectAs = Callable[[str], AbstractAsyncContextManager[asyncpg.Connection]]


@pytest.fixture
def connect_as(admin_url: str, role_passwords: RolePasswords) -> ConnectAs:
    """Opens a raw connection to the test database as `app_rw` or `agent_ro`."""
    passwords = {"app_rw": role_passwords.app_rw, "agent_ro": role_passwords.agent_ro}

    @asynccontextmanager
    async def _connect(role: str) -> AsyncIterator[asyncpg.Connection]:
        connection = await asyncpg.connect(role_url(admin_url, role, passwords[role], "postgresql"))
        try:
            yield connection
        finally:
            await connection.close()

    return _connect


BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"


@pytest.fixture(scope="session")
def database_env(admin_url: str, role_passwords: RolePasswords) -> dict[str, str]:
    """Environment for the real CLI entry points (alembic, seed) against the test DB."""
    return {
        "PATH": os.environ["PATH"],
        "HOME": os.environ.get("HOME", ""),
        "APP_ENV": "local",
        "DATABASE_URL_RW": role_url(
            admin_url, "app_rw", role_passwords.app_rw, "postgresql+asyncpg"
        ),
    }


BackendCli = Callable[..., subprocess.CompletedProcess[str]]


def _run_backend_cli(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, test-only
        [sys.executable, *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def backend_cli() -> BackendCli:
    """Runs `python <args>` in backend/ with the given environment (alembic, seed)."""
    return _run_backend_cli


@pytest.fixture(scope="session")
def seeded_db(database_env: dict[str, str]) -> dict[str, str]:
    """refunds_test migrated to head and freshly seeded, once per test session."""
    for args in (("-m", "alembic", "upgrade", "head"), ("-m", "seed.seed", "--reset")):
        result = _run_backend_cli(database_env, *args)
        assert result.returncode == 0, result.stderr or result.stdout
    return database_env


@pytest.fixture
def fresh_db(seeded_db: dict[str, str]) -> None:
    """Re-seeds refunds_test before a test that writes (decisions, refunds, runs)."""
    result = _run_backend_cli(seeded_db, "-m", "seed.seed", "--reset")
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.fixture
def make_settings(admin_url: str, role_passwords: RolePasswords) -> Callable[..., Settings]:
    rw_url = role_url(admin_url, "app_rw", role_passwords.app_rw, "postgresql+asyncpg")
    ro_url = role_url(admin_url, "agent_ro", role_passwords.agent_ro, "postgresql+asyncpg")

    def factory(**overrides: Any) -> Settings:
        values: dict[str, Any] = {
            "app_env": "local",
            "database_url_rw": rw_url,
            "database_url_ro": ro_url,
            **overrides,
        }
        if values["app_env"] == "production":
            values = {**PRODUCTION_SECRETS, **values}
        return Settings(**values)

    return factory


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    """A tiny stand-in for `npm run build` output."""
    build = tmp_path / "dist"
    (build / "assets").mkdir(parents=True)
    (build / "index.html").write_text(
        '<!doctype html><title>Member messages</title><div id="root"></div>'
    )
    (build / "assets" / "index-abc123.js").write_text("console.log('app')")
    (build / "favicon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    return build


@asynccontextmanager
async def _client_for(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        yield client


@pytest.fixture
def serve_app() -> Callable[[FastAPI], AbstractAsyncContextManager[AsyncClient]]:
    """Serves an app the test built itself (e.g. to add a route that misbehaves)."""
    return _client_for


@pytest.fixture
def serve(static_dir: Path) -> Serve:
    def _serve(
        settings: Settings, frontend_dir: Path = static_dir
    ) -> AbstractAsyncContextManager[AsyncClient]:
        return _client_for(create_app(settings, static_dir=frontend_dir))

    return _serve


@pytest.fixture
async def client(
    make_settings: Callable[..., Settings], serve: Serve
) -> AsyncIterator[AsyncClient]:
    async with serve(make_settings()) as test_client:
        yield test_client
