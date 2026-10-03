"""Rate limits apply to /api/* only (R-22, design §11)."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from httpx import AsyncClient

from app.core.config import Settings

Serve = Callable[..., AbstractAsyncContextManager[AsyncClient]]
REQUESTED_WITH = {"X-Requested-With": "refund-app"}


async def test_api_requests_over_the_limit_get_a_friendly_429(
    make_settings: Callable[..., Settings], serve: Serve
) -> None:
    async with serve(make_settings(rate_limit_default="3/minute")) as client:
        answers = [(await client.get("/api/health")).status_code for _ in range(4)]
        refused = await client.get("/api/health")

    assert answers == [200, 200, 200, 429]
    assert refused.json()["error"] == {
        "code": "rate_limited",
        "message": "Too many requests. Please wait a moment and try again.",
    }


async def test_the_app_pages_are_never_rate_limited(
    make_settings: Callable[..., Settings], serve: Serve
) -> None:
    async with serve(make_settings(rate_limit_default="1/minute")) as client:
        answers = {(await client.get("/")).status_code for _ in range(5)}

    assert answers == {200}


async def test_running_a_case_has_its_own_stricter_limit(
    make_settings: Callable[..., Settings], serve: Serve
) -> None:
    # Counted before the sign-in check, so a flood never reaches the flow or the database.
    async with serve(make_settings(rate_limit_run="1/minute")) as client:
        first = await client.post("/api/cases/5012/run", headers=REQUESTED_WITH)
        second = await client.post("/api/cases/5012/run", headers=REQUESTED_WITH)
        other_api = await client.get("/api/health")

    assert (first.status_code, second.status_code) == (401, 429)
    assert other_api.status_code == 200
