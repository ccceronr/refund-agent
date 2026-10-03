"""Pure ASGI middleware (no BaseHTTPMiddleware, so SSE streaming is never buffered).

Order, outermost first (see main.py): request id → security headers → unhandled errors
→ CORS (local only) → body size limit → routes.
"""

import re
import time
import uuid
from collections.abc import Mapping
from http import HTTPStatus

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import INTERNAL_ERROR, PAYLOAD_TOO_LARGE, error_response

REQUEST_ID_HEADER = "x-request-id"
CSP_HEADER = "content-security-policy"
_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")

# Design §1 "Serving" (OWASP A02). HSTS is added only in production.
SECURITY_HEADERS: Mapping[str, str] = {
    CSP_HEADER: (
        "default-src 'self'; object-src 'none'; frame-ancestors 'none'; "
        "base-uri 'self'; form-action 'self'"
    ),
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}
HSTS_HEADERS: Mapping[str, str] = {
    "strict-transport-security": "max-age=31536000; includeSubDomains",
}

log = structlog.get_logger(__name__)


def _on_response_start(message: Message) -> MutableHeaders | None:
    if message["type"] != "http.response.start":
        return None
    message.setdefault("headers", [])
    return MutableHeaders(scope=message)


class RequestIdMiddleware:
    """Reads or creates X-Request-ID, binds it to every log line, logs one line per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = _incoming_request_id(scope) or uuid.uuid4().hex
        status_code: int | None = None

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            headers = _on_response_start(message)
            if headers is not None:
                status_code = message["status"]
                headers[REQUEST_ID_HEADER] = request_id
            await send(message)

        started = time.perf_counter()
        with structlog.contextvars.bound_contextvars(request_id=request_id):
            try:
                await self.app(scope, receive, send_with_request_id)
            finally:
                log.info(
                    "request",
                    method=scope["method"],
                    path=scope["path"],
                    status=status_code,
                    duration_ms=round((time.perf_counter() - started) * 1000, 1),
                )


def _incoming_request_id(scope: Scope) -> str | None:
    # Only safe characters, so a client can't inject fake fields into our logs.
    value = Headers(scope=scope).get(REQUEST_ID_HEADER)
    return value if value and _SAFE_REQUEST_ID.fullmatch(value) else None


class SecurityHeadersMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        headers: Mapping[str, str],
        csp_exempt_paths: frozenset[str] = frozenset(),
    ) -> None:
        self.app = app
        self.headers = headers
        self.csp_exempt_paths = csp_exempt_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        skip_csp = scope["path"] in self.csp_exempt_paths

        async def send_with_headers(message: Message) -> None:
            response_headers = _on_response_start(message)
            if response_headers is not None:
                for name, value in self.headers.items():
                    if not (skip_csp and name == CSP_HEADER):
                        response_headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)


class UnhandledErrorMiddleware:
    """Any unexpected exception → logged with the request id, friendly JSON 500 (OWASP A10)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            response_started = response_started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:
            log.exception("unhandled_error", path=scope["path"])
            if response_started:
                raise
            response = error_response(HTTPStatus.INTERNAL_SERVER_ERROR, *INTERNAL_ERROR)
            await response(scope, receive, send)


class _BodyTooLarge(StarletteHTTPException):
    # An HTTPException, so FastAPI re-raises it from body parsing instead of turning it
    # into a generic 400, and the normal error handler answers with the JSON 413.
    def __init__(self) -> None:
        super().__init__(status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)


class RequestBodyLimitMiddleware:
    """Rejects bodies over `max_bytes` with 413, by declared length or while streaming."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if _declared_length(scope) > self.max_bytes:
            await _payload_too_large(scope, receive, send)
            return
        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            response_started = response_started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _BodyTooLarge:
            # Only reached when the body is read outside the routes' error handling.
            if response_started:
                raise
            await _payload_too_large(scope, receive, send)


def _declared_length(scope: Scope) -> int:
    value = Headers(scope=scope).get("content-length", "")
    return int(value) if value.isdigit() else 0


async def _payload_too_large(scope: Scope, receive: Receive, send: Send) -> None:
    response = error_response(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, *PAYLOAD_TOO_LARGE)
    await response(scope, receive, send)
