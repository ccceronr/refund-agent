"""The built SPA is served by the app itself (design §1 "Serving")."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from app.api.frontend import FrontendBuildMissing
from app.core.config import Settings
from app.main import create_app

BROWSER_NAVIGATION = {"Accept": "text/html,application/xhtml+xml"}
IMMUTABLE = "public, max-age=31536000, immutable"


async def test_browser_navigation_to_an_app_route_gets_index_without_cache(
    client: AsyncClient,
) -> None:
    response = await client.get("/cases/5012", headers=BROWSER_NAVIGATION)

    assert response.status_code == 200
    assert '<div id="root">' in response.text
    assert response.headers["cache-control"] == "no-cache"


async def test_hashed_asset_is_cached_for_a_year(client: AsyncClient) -> None:
    response = await client.get("/assets/index-abc123.js")

    assert response.status_code == 200
    assert response.text == "console.log('app')"
    assert response.headers["cache-control"] == IMMUTABLE


async def test_missing_asset_is_a_404_not_the_index(client: AsyncClient) -> None:
    response = await client.get("/assets/missing-999.js", headers=BROWSER_NAVIGATION)

    assert response.status_code == 404
    assert '<div id="root">' not in response.text


async def test_missing_asset_is_never_cached_as_immutable(client: AsyncClient) -> None:
    response = await client.get("/assets/missing-999.js")

    assert response.headers.get("cache-control") != IMMUTABLE


async def _raw_get(app: Any, raw_path: str) -> tuple[int, dict[str, str], bytes]:
    """Sends the path exactly as given, like `curl --path-as-is` (httpx would normalize it)."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": raw_path,
        "raw_path": raw_path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"testserver"), (b"accept", b"text/html")],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    await app(scope, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    headers = {name.decode(): value.decode() for name, value in start["headers"]}
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return start["status"], headers, body


@pytest.mark.parametrize(
    "dot_path",
    ["/assets/../index.html", "/assets/../../outside.txt", "/assets/%2e%2e/index.html"],
)
async def test_dot_segments_under_assets_never_escape_the_assets_folder(
    make_settings: Callable[..., Settings], static_dir: Path, dot_path: str
) -> None:
    (static_dir.parent / "outside.txt").write_text("not part of the build")
    app = create_app(make_settings(), static_dir=static_dir)

    status, headers, body = await _raw_get(app, dot_path)

    assert status == 404
    assert headers.get("cache-control") != IMMUTABLE
    assert b'<div id="root">' not in body


async def test_file_at_the_build_root_is_served_without_long_cache(client: AsyncClient) -> None:
    response = await client.get("/favicon.svg")

    assert response.status_code == 200
    assert "<svg" in response.text
    assert response.headers["cache-control"] == "no-cache"


async def test_api_still_works_locally_without_a_frontend_build(
    make_settings: Callable[..., Settings], serve, tmp_path: Path
) -> None:
    async with serve(make_settings(), frontend_dir=tmp_path / "no-build") as client:
        response = await client.get("/api/health")

    assert response.status_code == 200


def test_production_refuses_to_start_without_a_frontend_build(
    make_settings: Callable[..., Settings], tmp_path: Path
) -> None:
    with pytest.raises(FrontendBuildMissing):
        create_app(make_settings(app_env="production"), static_dir=tmp_path / "no-build")
