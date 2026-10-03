"""CORS: never in production (one origin); optional locally (design §1 "Serving")."""

from collections.abc import Callable

from app.core.config import Settings

PREFLIGHT = {
    "Origin": "http://localhost:5173",
    "Access-Control-Request-Method": "POST",
}


async def test_configured_origin_is_allowed_locally(
    make_settings: Callable[..., Settings], serve
) -> None:
    settings = make_settings(cors_origins=["http://localhost:5173"])

    async with serve(settings) as client:
        response = await client.options("/api/health", headers=PREFLIGHT)

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


async def test_no_cors_in_production_even_with_origins_configured(
    make_settings: Callable[..., Settings], serve
) -> None:
    settings = make_settings(app_env="production", cors_origins=["http://localhost:5173"])

    async with serve(settings) as client:
        response = await client.options("/api/health", headers=PREFLIGHT)

    assert "access-control-allow-origin" not in response.headers
