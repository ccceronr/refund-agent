"""Sign-in, sessions and request guards (design §4.0; OWASP A01, A07; tasks P6)."""

import re
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.config import Settings
from app.main import create_app

REQUESTED_WITH = {"X-Requested-With": "refund-app"}
WRONG_CREDENTIALS = "Wrong username or password."
# design §4.0: the only endpoints anyone may call without signing in.
PUBLIC = {("GET", "/api/health"), ("HEAD", "/api/health"), ("POST", "/api/auth/login")}

ServeApp = Callable[[FastAPI], AbstractAsyncContextManager[AsyncClient]]


@pytest.fixture
def app(
    seeded_db: dict[str, str], make_settings: Callable[..., Settings], static_dir: Path
) -> FastAPI:
    return create_app(make_settings(session_secret="t" * 48), static_dir=static_dir)


@pytest.fixture
async def client(app: FastAPI, serve_app: ServeApp) -> AsyncIterator[AsyncClient]:
    async with serve_app(app) as test_client:
        yield test_client


async def sign_in(client: AsyncClient, username: str, password: str) -> Any:
    return await client.post(
        "/api/auth/login", json={"username": username, "password": password}, headers=REQUESTED_WITH
    )


async def test_signing_in_starts_a_session_for_that_staff_member(
    client: AsyncClient, staff_passwords: dict[str, str]
) -> None:
    signed_in = await sign_in(client, "luis", staff_passwords["luis"])
    me = await client.get("/api/auth/me")

    assert signed_in.status_code == 200
    assert signed_in.json() == {"name": "Luis", "role": "staff"}
    assert me.json() == {"name": "Luis", "role": "staff"}


async def test_the_session_cookie_is_http_only_and_same_site_strict(
    client: AsyncClient, staff_passwords: dict[str, str]
) -> None:
    signed_in = await sign_in(client, "marta", staff_passwords["marta"])

    cookie = signed_in.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "max-age=28800" in cookie  # 8 h


@pytest.mark.parametrize(
    ("username", "password"),
    [("luis", "not-the-password"), ("nobody", "not-the-password"), ("", "x")],
    ids=["wrong-password", "unknown-user", "empty-username"],
)
async def test_a_failed_sign_in_never_says_which_part_was_wrong(
    client: AsyncClient, username: str, password: str
) -> None:
    response = await sign_in(client, username, password)

    assert response.status_code in {401, 422}
    if response.status_code == 401:
        assert response.json()["error"]["message"] == WRONG_CREDENTIALS
    assert "set-cookie" not in response.headers


async def test_the_sixth_failed_attempt_is_throttled_even_with_the_right_password(
    client: AsyncClient, staff_passwords: dict[str, str]
) -> None:
    for _ in range(5):
        assert (await sign_in(client, "luis", "wrong")).status_code == 401

    response = await sign_in(client, "luis", staff_passwords["luis"])

    assert response.status_code == 429
    assert response.json()["error"]["message"] == "Too many attempts. Try again in a few minutes."


async def test_signing_out_ends_the_session(
    client: AsyncClient, staff_passwords: dict[str, str]
) -> None:
    await sign_in(client, "luis", staff_passwords["luis"])

    signed_out = await client.post("/api/auth/logout", headers=REQUESTED_WITH)
    me = await client.get("/api/auth/me")

    assert signed_out.status_code == 204
    assert me.status_code == 401


async def test_sign_ins_are_audited_without_usernames_or_passwords(
    client: AsyncClient, staff_passwords: dict[str, str], connect_as
) -> None:
    await sign_in(client, "luis", "wrong-password-xyz")
    await sign_in(client, "luis", staff_passwords["luis"])

    async with connect_as("app_rw") as db:
        rows = await db.fetch(
            "SELECT event, actor_id, details::text FROM audit_log"
            " WHERE event LIKE 'login%' ORDER BY id"
        )
    assert [(r["event"], r["actor_id"]) for r in rows][-2:] == [
        ("login_failed", "S14"),
        ("login_succeeded", "S14"),
    ]
    assert not any("wrong-password-xyz" in r["details"] or "luis" in r["details"] for r in rows)


def _protected_requests(app: FastAPI) -> list[tuple[str, str]]:
    # The OpenAPI schema lists every API operation (docs are on outside production).
    requests = []
    for path, operations in app.openapi()["paths"].items():
        concrete = re.sub(r"\{[^}]+\}", "5012", path)
        requests += [(m.upper(), concrete) for m in operations if (m.upper(), path) not in PUBLIC]
    return requests


async def test_every_endpoint_but_health_and_sign_in_needs_a_session(
    app: FastAPI, client: AsyncClient
) -> None:
    # Deny by default (OWASP A01): a new route without the session check fails this test.
    requests = _protected_requests(app)

    responses = {(m, p): await client.request(m, p, headers=REQUESTED_WITH) for m, p in requests}

    assert {("POST", "/api/cases/5012/decision"), ("GET", "/api/cases")} <= set(requests)
    assert {key: r.status_code for key, r in responses.items()} == dict.fromkeys(requests, 401)


async def test_a_change_without_the_requested_with_header_is_refused(
    client: AsyncClient, staff_passwords: dict[str, str]
) -> None:
    response = await client.post(
        "/api/auth/login", json={"username": "luis", "password": staff_passwords["luis"]}
    )

    assert response.status_code == 403
    assert "set-cookie" not in response.headers
