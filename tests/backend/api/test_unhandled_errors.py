"""Unexpected errors become a friendly JSON 500, never a stack trace (R-21, OWASP A10)."""

import re
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app

SECRET_DETAIL = "db password is hunter2"


def _app_with_a_failing_route(settings: Settings, static_dir: Path) -> FastAPI:
    app = create_app(settings, static_dir=static_dir)

    async def explode() -> None:
        raise RuntimeError(SECRET_DETAIL)

    app.add_api_route("/test-only/boom", explode)
    return app


async def test_unhandled_exception_becomes_a_friendly_json_500(
    make_settings: Callable[..., Settings], serve_app, static_dir: Path
) -> None:
    app = _app_with_a_failing_route(make_settings(), static_dir)

    async with serve_app(app) as client:
        response = await client.get("/test-only/boom")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert SECRET_DETAIL not in response.text
    assert "Traceback" not in response.text


async def test_the_500_still_carries_request_id_and_security_headers(
    make_settings: Callable[..., Settings], serve_app, static_dir: Path
) -> None:
    app = _app_with_a_failing_route(make_settings(), static_dir)

    async with serve_app(app) as client:
        response = await client.get("/test-only/boom")

    assert re.fullmatch(r"[0-9a-f]{32}", response.headers["x-request-id"])
    assert response.headers["x-frame-options"] == "DENY"
