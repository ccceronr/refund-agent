"""Security headers on every response, from one middleware (design §1 "Serving", OWASP A02)."""

from collections.abc import Callable

import pytest
from httpx import AsyncClient

from app.core.config import Settings

PATHS = [
    ("/api/health", {}),
    ("/api/unknown", {}),
    ("/cases/5012", {"Accept": "text/html"}),
    ("/assets/index-abc123.js", {}),
]


@pytest.mark.parametrize(("path", "headers"), PATHS)
async def test_every_response_carries_the_security_headers(
    client: AsyncClient, path: str, headers: dict[str, str]
) -> None:
    response = await client.get(path, headers=headers)

    csp = response.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in response.headers["permissions-policy"]


async def test_hsts_is_not_sent_locally(client: AsyncClient) -> None:
    response = await client.get("/api/health")

    assert "strict-transport-security" not in response.headers


async def test_hsts_is_sent_in_production(make_settings: Callable[..., Settings], serve) -> None:
    async with serve(make_settings(app_env="production")) as client:
        response = await client.get("/api/health")

    assert response.headers["strict-transport-security"].startswith("max-age=")
