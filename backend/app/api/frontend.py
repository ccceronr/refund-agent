"""Serves the built SPA from the app itself, with FastAPI's `frontend()` (design §1 "Serving").

API path operations always win; frontend files are only checked when no route matched.
The frontend never answers under /api, so an unknown API path is the JSON 404 and a
wrong method on a known one is Starlette's own 405, never index.html.
"""

from collections.abc import Awaitable, Callable
from http import HTTPStatus
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response

API_PREFIX = "/api"
ASSETS_PREFIX = "/assets/"
# Vite puts a content hash in every /assets/ file name, so they never change in place.
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
# index.html (and other unhashed files) must be revalidated so a deploy shows up at once.
REVALIDATE_CACHE = "no-cache"


class FrontendBuildMissing(RuntimeError):
    pass


def has_frontend_build(static_dir: Path) -> bool:
    return (static_dir / "index.html").is_file()


def mount_frontend(app: FastAPI, static_dir: Path) -> None:
    router = APIRouter(
        dependencies=[
            Depends(_reject_api_paths),
            Depends(_reject_missing_assets(static_dir)),
            Depends(_set_cache_headers),
        ]
    )
    router.frontend("/", directory=static_dir, check_dir=True)
    app.include_router(router)


def is_api_path(path: str) -> bool:
    return path == API_PREFIX or path.startswith(f"{API_PREFIX}/")


async def _reject_api_paths(request: Request) -> None:
    if is_api_path(request.url.path):
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)


def _reject_missing_assets(static_dir: Path) -> Callable[[Request], Awaitable[None]]:
    # frontend() falls back to index.html for any HTML navigation, /assets/ included.
    # A hashed asset URL must never answer with the page (and cache it for a year), and
    # dot segments (`/assets/../x`) must not reveal whether files exist elsewhere.
    assets_dir = (static_dir / ASSETS_PREFIX.strip("/")).resolve()

    async def dependency(request: Request) -> None:
        path = request.url.path
        if not path.startswith(ASSETS_PREFIX):
            return
        candidate = (static_dir / path.lstrip("/")).resolve()
        if not (candidate.is_relative_to(assets_dir) and candidate.is_file()):
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND)

    return dependency


async def _set_cache_headers(request: Request, response: Response) -> None:
    hashed = request.url.path.startswith(ASSETS_PREFIX)
    response.headers["Cache-Control"] = IMMUTABLE_CACHE if hashed else REVALIDATE_CACHE
