"""App factory: wires routers, error handlers, middleware and the SPA (design §1, §4).

Run with: uvicorn app.main:build_app --factory
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.errors import register_error_handlers
from app.api.frontend import (
    API_PREFIX,
    FrontendBuildMissing,
    has_frontend_build,
    mount_frontend,
)
from app.api.health import router as health_router
from app.api.middleware import (
    HSTS_HEADERS,
    SECURITY_HEADERS,
    RequestBodyLimitMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
    UnhandledErrorMiddleware,
)
from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.version import APP_VERSION
from app.db.engines import create_rw_engine

STATIC_DIR = Path(__file__).parent / "static"
DOCS_URL = "/docs"
OPENAPI_URL = "/openapi.json"
CORS_ALLOWED_HEADERS = ["Content-Type", "Idempotency-Key", "X-Requested-With", "X-Request-ID"]

log = structlog.get_logger(__name__)


def create_app(settings: Settings, static_dir: Path = STATIC_DIR) -> FastAPI:
    engine = create_rw_engine(settings)
    docs_enabled = not settings.is_production
    app = FastAPI(
        title="Fee refund agent",
        version=APP_VERSION,
        docs_url=DOCS_URL if docs_enabled else None,
        redoc_url=None,
        openapi_url=OPENAPI_URL if docs_enabled else None,
        lifespan=_dispose_on_shutdown(engine),
    )
    app.state.settings = settings
    app.state.rw_engine = engine
    register_error_handlers(app)
    app.include_router(health_router, prefix=API_PREFIX)
    _serve_frontend(app, settings, static_dir)
    _add_middleware(app, settings, docs_enabled)
    return app


def build_app() -> FastAPI:
    """Process entry point: logging first, then settings from the environment."""
    configure_logging()
    return create_app(Settings())


def _dispose_on_shutdown(
    engine: AsyncEngine,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await engine.dispose()

    return lifespan


def _serve_frontend(app: FastAPI, settings: Settings, static_dir: Path) -> None:
    if has_frontend_build(static_dir):
        mount_frontend(app, static_dir)
        return
    if settings.is_production:
        raise FrontendBuildMissing(f"No frontend build found in {static_dir}")
    # Local development: the API runs alone while Vite serves the frontend.
    log.warning("frontend_build_missing", directory=str(static_dir))


def _add_middleware(app: FastAPI, settings: Settings, docs_enabled: bool) -> None:
    # add_middleware wraps: the last one added runs first (outermost).
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    if settings.cors_origins and not settings.is_production:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=CORS_ALLOWED_HEADERS,
        )
    app.add_middleware(UnhandledErrorMiddleware)
    headers = {**SECURITY_HEADERS, **(HSTS_HEADERS if settings.is_production else {})}
    # Swagger UI (local only) needs a CDN script and inline setup that the CSP blocks.
    docs_paths = frozenset({DOCS_URL, f"{DOCS_URL}/oauth2-redirect"} if docs_enabled else ())
    app.add_middleware(SecurityHeadersMiddleware, headers=headers, csp_exempt_paths=docs_paths)
    app.add_middleware(RequestIdMiddleware)
