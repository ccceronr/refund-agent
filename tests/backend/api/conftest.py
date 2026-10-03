"""Signed-in API clients over a freshly seeded database, with the models faked."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any

import pytest
from fakes import FakeWriter, ScriptedDecider
from fastapi import FastAPI
from httpx import AsyncClient

from app.agents.run_case import CaseRunner, RunResult
from app.agents.steps import EventSink
from app.core.config import Settings
from app.db.engines import create_ro_engine, create_rw_engine
from app.main import create_app

REQUESTED_WITH = {"X-Requested-With": "refund-app"}

SignIn = Callable[[AsyncClient, str], Awaitable[None]]
Prepare = Callable[..., Awaitable[RunResult]]


@pytest.fixture
def staff_app(fresh_db: None, make_settings: Callable[..., Settings], static_dir: Path) -> FastAPI:
    settings = make_settings(session_secret="t" * 48)
    app = create_app(settings, static_dir=static_dir)
    app.state.runner_factory = _fake_runner_factory(settings)
    return app


@pytest.fixture
async def api(
    staff_app: FastAPI, serve_app: Callable[[FastAPI], AbstractAsyncContextManager[AsyncClient]]
) -> AsyncIterator[AsyncClient]:
    async with serve_app(staff_app) as client:
        yield client


@pytest.fixture
def sign_in(staff_passwords: dict[str, str]) -> SignIn:
    async def _sign_in(client: AsyncClient, username: str) -> None:
        body = {"username": username, "password": staff_passwords[username]}
        response = await client.post("/api/auth/login", json=body, headers=REQUESTED_WITH)
        assert response.status_code == 200, response.text

    return _sign_in


@pytest.fixture
def prepare(make_settings: Callable[..., Settings]) -> Prepare:
    """Prepares a case through the real flow and services, with the models faked."""

    async def _prepare(case_id: int, decider: Any = None) -> RunResult:
        settings = make_settings()
        ro, rw = create_ro_engine(settings), create_rw_engine(settings)
        runner = CaseRunner(settings=settings, ro_engine=ro, rw_engine=rw,
                            decider=decider or ScriptedDecider(), writer=FakeWriter())  # fmt: skip
        try:
            return await runner.run(case_id)
        finally:
            await ro.dispose()
            await rw.dispose()

    return _prepare


def _fake_runner_factory(settings: Settings) -> Callable[[EventSink], CaseRunner]:
    ro, rw = create_ro_engine(settings), create_rw_engine(settings)

    def factory(events: EventSink) -> CaseRunner:
        return CaseRunner(settings=settings, ro_engine=ro, rw_engine=rw, decider=ScriptedDecider(),
                          writer=FakeWriter(), events=events)  # fmt: skip

    return factory
