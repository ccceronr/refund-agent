"""GET /api/health: liveness plus a database check (design §4, Railway health check)."""

from http import HTTPStatus
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.dependencies import AppSettings, RwEngine
from app.core.version import APP_VERSION
from app.db.health import database_is_reachable

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok", "error"]
    db: Literal["ok", "error"]
    version: str


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={HTTPStatus.SERVICE_UNAVAILABLE: {"model": HealthResponse}},
)
async def health(engine: RwEngine, settings: AppSettings) -> JSONResponse:
    reachable = await database_is_reachable(engine, settings.db_connect_timeout_seconds)
    state: Literal["ok", "error"] = "ok" if reachable else "error"
    body = HealthResponse(status=state, db=state, version=APP_VERSION)
    status_code = HTTPStatus.OK if reachable else HTTPStatus.SERVICE_UNAVAILABLE
    return JSONResponse(body.model_dump(), status_code=status_code)


# HEAD too: uptime monitors and `curl -I` use it by default. Kept out of the OpenAPI
# schema so the GET operation stays the only documented one.
router.add_api_route("/health", health, methods=["HEAD"], include_in_schema=False)
