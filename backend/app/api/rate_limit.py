"""Rate limits for /api/* only (R-22, design §11): 60/min per client, 10/min on /run.

A dependency of the /api router, so every API route is limited by default and the SPA
files never are. slowapi checks one limit per request, so the dependency picks it.
"""

from fastapi import Request
from slowapi import Limiter

from app.core.config import Settings

# Railway's edge proxy sets this to the client's address (Railway docs, "Specs & Limits").
EDGE_CLIENT_IP_HEADER = "x-real-ip"
UNKNOWN_CLIENT = "unknown"
RUN_PATH_SUFFIX = "/run"


def build_limiter(settings: Settings) -> Limiter:
    key = _client_ip_behind_railway if settings.is_production else _client_ip
    return Limiter(key_func=key)


class RateLimits:
    """The two checks of one app, each with its own counter per client."""

    def __init__(self, limiter: Limiter, settings: Settings) -> None:
        self.api = limiter.limit(settings.rate_limit_default)(api_request)
        self.runs = limiter.limit(settings.rate_limit_run)(run_request)


async def api_request(request: Request) -> None:
    """Counts one API request (slowapi keys the counter by this function's name)."""


async def run_request(request: Request) -> None:
    """Counts one run of the flow (slowapi keys the counter by this function's name)."""


async def enforce_rate_limit(request: Request) -> None:
    """Router dependency for /api; RateLimitExceeded becomes the JSON 429 (api/errors.py)."""
    limits: RateLimits = request.app.state.rate_limits
    check = limits.runs if _is_run_request(request) else limits.api
    await check(request=request)


def _is_run_request(request: Request) -> bool:
    return request.method == "POST" and request.url.path.endswith(RUN_PATH_SUFFIX)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else UNKNOWN_CLIENT


def _client_ip_behind_railway(request: Request) -> str:
    # Only trusted in production, where every request comes through Railway's edge.
    # Locally a client could send the header itself.
    return request.headers.get(EDGE_CLIENT_IP_HEADER) or _client_ip(request)
