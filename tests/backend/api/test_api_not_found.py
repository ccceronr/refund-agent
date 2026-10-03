"""An unknown /api/... path is a JSON 404, never the SPA (design §1 "Serving", R-21)."""

from collections.abc import Callable
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.config import Settings


@pytest.mark.parametrize("accept", ["application/json", "text/html,application/xhtml+xml"])
async def test_unknown_api_path_returns_the_json_404(client: AsyncClient, accept: str) -> None:
    response = await client.get("/api/does-not-exist", headers={"Accept": accept})

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
    assert response.json()["error"]["code"] == "not_found"
    assert response.json()["error"]["message"]


async def test_unknown_api_path_with_post_returns_the_json_404(client: AsyncClient) -> None:
    response = await client.post("/api/cases/1/nothing-here", json={})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_wrong_method_on_a_known_api_path_is_405_not_404(client: AsyncClient) -> None:
    response = await client.post("/api/health", json={})

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert "GET" in response.headers["allow"].split(", ")


async def test_known_api_route_still_answers(client: AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200


async def test_unknown_api_path_is_the_json_404_without_a_frontend_build_too(
    make_settings: Callable[..., Settings], serve, tmp_path: Path
) -> None:
    async with serve(make_settings(), frontend_dir=tmp_path / "no-build") as client:
        response = await client.get("/api/does-not-exist", headers={"Accept": "text/html"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_bare_api_prefix_is_not_the_spa(client: AsyncClient) -> None:
    response = await client.get("/api", headers={"Accept": "text/html"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
