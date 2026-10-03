"""FastAPI docs are a local convenience only (CLAUDE.md security checklist, OWASP A02)."""

from collections.abc import Callable

from httpx import AsyncClient

from app.core.config import Settings


async def test_api_docs_are_available_locally(client: AsyncClient) -> None:
    docs = await client.get("/docs")
    schema = await client.get("/openapi.json")

    assert docs.status_code == 200
    assert schema.status_code == 200


async def test_local_docs_page_is_not_blocked_by_the_csp(client: AsyncClient) -> None:
    # Swagger UI loads its script from a CDN and inlines its setup; CSP would block it.
    response = await client.get("/docs")

    assert "content-security-policy" not in response.headers


async def test_api_docs_are_disabled_in_production(
    make_settings: Callable[..., Settings], serve
) -> None:
    async with serve(make_settings(app_env="production")) as client:
        docs = await client.get("/docs")
        schema = await client.get("/openapi.json")

    assert docs.status_code == 404
    assert schema.status_code == 404
