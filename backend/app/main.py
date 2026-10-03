"""App factory: wires routers, error handlers, middleware and the SPA (design §1, §4).

Run with: uvicorn app.main:build_app --factory
"""

import secrets
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import anthropic
import httpx
import structlog
from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.middleware.sessions import SessionMiddleware

from app.agents.clients import anthropic_client, jev_http_client
from app.agents.run_case import CaseRunner, flow_models
from app.agents.steps import EventSink
from app.api.auth import router as auth_router
from app.api.cases import router as cases_router
from app.api.dependencies import current_staff
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
    RequireRequestedWithMiddleware,
    SecurityHeadersMiddleware,
    UnhandledErrorMiddleware,
)
from app.api.policies import router as policies_router
from app.api.rate_limit import RateLimits, build_limiter, enforce_rate_limit
from app.core.config import Settings
from app.core.logging import configure_logging
from app.core.version import APP_VERSION
from app.db.engines import create_ro_engine, create_rw_engine
from app.rules.model import Thresholds
from app.services.auth import AuthService, LoginThrottle
from app.services.decisions import DecisionService
from app.services.refunds import RefundService
from app.services.runs import recover_interrupted_runs

STATIC_DIR = Path(__file__).parent / "static"
DOCS_URL = "/docs"
OPENAPI_URL = "/openapi.json"
CORS_ALLOWED_HEADERS = ["Content-Type", "Idempotency-Key", "X-Requested-With", "X-Request-ID"]
SESSION_COOKIE = "session"

log = structlog.get_logger(__name__)


def create_app(settings: Settings, static_dir: Path = STATIC_DIR) -> FastAPI:
    engine = create_rw_engine(settings)
    ro_engine = create_ro_engine(settings) if settings.database_url_ro else None
    clients = ModelClients(jev_http_client(settings), anthropic_client(settings))
    docs_enabled = not settings.is_production
    app = FastAPI(
        title="Fee refund agent",
        version=APP_VERSION,
        docs_url=DOCS_URL if docs_enabled else None,
        redoc_url=None,
        openapi_url=OPENAPI_URL if docs_enabled else None,
        lifespan=_dispose_on_shutdown(engine, ro_engine, clients),
    )
    app.state.settings = settings
    app.state.rw_engine = engine
    _add_services(app, settings, engine, ro_engine, clients)
    register_error_handlers(app)
    _add_api_routes(app)
    _serve_frontend(app, settings, static_dir)
    _add_middleware(app, settings, docs_enabled)
    return app


def build_app() -> FastAPI:
    """Process entry point: logging first, then settings from the environment."""
    configure_logging()
    return create_app(Settings())


@dataclass(frozen=True)
class ModelClients:
    jev: httpx.AsyncClient
    claude: anthropic.AsyncAnthropic


def _dispose_on_shutdown(
    engine: AsyncEngine, ro_engine: AsyncEngine | None, clients: ModelClients
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await _recover_interrupted_runs(engine)
        yield
        await clients.jev.aclose()
        await clients.claude.close()
        if ro_engine is not None:
            await ro_engine.dispose()
        await engine.dispose()

    return lifespan


def _add_services(
    app: FastAPI,
    settings: Settings,
    engine: AsyncEngine,
    ro_engine: AsyncEngine | None,
    clients: ModelClients,
) -> None:
    throttle = LoginThrottle(settings.login_max_failures, settings.login_lockout_seconds)
    app.state.auth = AuthService(engine, throttle)
    app.state.decisions = DecisionService(engine, RefundService(Thresholds.from_settings(settings)))
    app.state.limiter = build_limiter(settings)
    app.state.rate_limits = RateLimits(app.state.limiter, settings)
    app.state.running = set()  # runs in flight, kept referenced until they finish
    decider, writer = flow_models(settings, clients.jev, clients.claude)

    def runner_factory(events: EventSink) -> CaseRunner:
        if ro_engine is None:
            raise RuntimeError("DATABASE_URL_RO is not set: the flow needs the read-only role")
        return CaseRunner(
            settings=settings,
            ro_engine=ro_engine,
            rw_engine=engine,
            decider=decider,
            writer=writer,
            events=events,
        )

    app.state.runner_factory = runner_factory


def _add_api_routes(app: FastAPI) -> None:
    # R-22: every API route is rate limited. OWASP A01: deny by default; only health and
    # sign-in are public.
    api = APIRouter(prefix=API_PREFIX, dependencies=[Depends(enforce_rate_limit)])
    api.include_router(health_router)
    api.include_router(auth_router)
    api.include_router(cases_router, dependencies=[Depends(current_staff)])
    api.include_router(policies_router, dependencies=[Depends(current_staff)])
    app.include_router(api)


async def _recover_interrupted_runs(engine: AsyncEngine) -> None:
    # design §5.2: runs left `running` by a crash become TIMEOUT manual reviews. If the
    # database is down the app still starts, so /api/health can report it.
    try:
        await recover_interrupted_runs(engine)
    except (SQLAlchemyError, OSError) as error:
        log.error("run_recovery_failed", error=type(error).__name__)


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
    app.add_middleware(
        SessionMiddleware,
        secret_key=_session_secret(settings),
        session_cookie=SESSION_COOKIE,
        max_age=settings.session_max_age_seconds,
        same_site="strict",
        https_only=settings.is_production,
    )
    app.add_middleware(RequireRequestedWithMiddleware)
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


def _session_secret(settings: Settings) -> str:
    # Production refuses to start without a strong secret (config). Locally a missing one
    # gets a random secret per process: sessions then end when the app restarts.
    if settings.session_secret_value:
        return settings.session_secret_value
    log.warning("session_secret_missing", effect="sign-ins last until the app restarts")
    return secrets.token_urlsafe(48)
