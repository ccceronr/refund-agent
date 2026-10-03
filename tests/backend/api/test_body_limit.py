"""Request bodies are size-limited in the app, since no proxy does it (design §1 "Serving")."""

from collections.abc import AsyncIterator, Callable
from pathlib import Path

from fastapi import FastAPI, Request
from pydantic import BaseModel

from app.core.config import Settings
from app.main import create_app

LIMIT = 16


class Note(BaseModel):
    text: str


def _app_with_body_routes(settings: Settings, static_dir: Path) -> FastAPI:
    app = create_app(settings, static_dir=static_dir)

    async def raw_length(request: Request) -> dict[str, int]:
        return {"length": len(await request.body())}

    async def typed_note(note: Note) -> dict[str, int]:
        return {"length": len(note.text)}

    app.add_api_route("/test-only/raw", raw_length, methods=["POST"])
    app.add_api_route("/test-only/typed", typed_note, methods=["POST"])
    return app


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


async def test_declared_body_over_the_limit_is_rejected_with_413(
    make_settings: Callable[..., Settings], serve
) -> None:
    async with serve(make_settings(max_request_body_bytes=LIMIT)) as client:
        response = await client.post("/api/anything", content=b"x" * (LIMIT + 1))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


async def test_streamed_body_over_the_limit_is_rejected_with_413(
    make_settings: Callable[..., Settings], serve_app, static_dir: Path
) -> None:
    app = _app_with_body_routes(make_settings(max_request_body_bytes=LIMIT), static_dir)

    async with serve_app(app) as client:
        response = await client.post("/test-only/raw", content=_chunks(b"x" * 10, b"y" * 10))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


async def test_streamed_json_body_over_the_limit_is_413_not_a_parsing_error(
    make_settings: Callable[..., Settings], serve_app, static_dir: Path
) -> None:
    app = _app_with_body_routes(make_settings(max_request_body_bytes=LIMIT), static_dir)
    body = b'{"text": "' + b"z" * LIMIT + b'"}'

    async with serve_app(app) as client:
        response = await client.post(
            "/test-only/typed",
            content=_chunks(body[:8], body[8:]),
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 413


async def test_body_within_the_limit_reaches_the_route(
    make_settings: Callable[..., Settings], serve_app, static_dir: Path
) -> None:
    app = _app_with_body_routes(make_settings(max_request_body_bytes=LIMIT), static_dir)

    async with serve_app(app) as client:
        response = await client.post("/test-only/raw", content=b"x" * LIMIT)

    assert response.status_code == 200
    assert response.json() == {"length": LIMIT}
