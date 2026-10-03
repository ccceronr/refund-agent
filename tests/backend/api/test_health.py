"""GET /api/health (design §4, tasks P0)."""

from collections.abc import Callable
from importlib.metadata import version

from httpx import AsyncClient

from app.core.config import Settings

UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://app_rw:unused@127.0.0.1:1/refunds"


async def test_health_is_ok_when_the_database_answers(client: AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok", "version": version("fee-refund-agent")}


async def test_health_answers_head_requests_from_uptime_monitors(client: AsyncClient) -> None:
    response = await client.head("/api/health")

    assert response.status_code == 200


async def test_health_is_503_when_the_database_is_unreachable(
    make_settings: Callable[..., Settings], serve
) -> None:
    settings = make_settings(database_url_rw=UNREACHABLE_DATABASE_URL)

    async with serve(settings) as client:
        response = await client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["status"] == "error"
    assert response.json()["db"] == "error"
