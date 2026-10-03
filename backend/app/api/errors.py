"""The one place that maps errors to the API shape {"error": {"code", "message"}} (R-21).

Messages are plain language for the UI (ui.md §3): never exception text, codes from
other systems, or stack traces.
"""

from collections.abc import Awaitable, Callable
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.rules.texts import ALREADY_REFUNDED_MESSAGE, NO_FEE_MESSAGE
from app.services.errors import (
    ApprovalNotAllowed,
    CaseAlreadyDecided,
    CaseNotFound,
    FeeAlreadyRefunded,
    InvalidDecision,
    NoFeeIdentified,
    RunInProgress,
    RunLimitReached,
    TooManyAttempts,
    WrongCredentials,
)

INTERNAL_ERROR = ("internal_error", "Something went wrong on our side. Please try again.")
VALIDATION_ERROR = ("validation_error", "Some of the information sent isn't valid.")
PAYLOAD_TOO_LARGE = ("payload_too_large", "That's more data than we accept in one request.")
REQUEST_BLOCKED = (
    "request_blocked",
    "This request was blocked for your security. Reload the page and try again.",
)


class NotSignedIn(PermissionError):
    """No valid session (design §4.0): the UI shows the sign-in screen."""


# Domain errors → (status, code, plain message). One place, as CLAUDE.md asks.
_DOMAIN_ERRORS: dict[type[Exception], tuple[int, str, str]] = {
    NotSignedIn: (HTTPStatus.UNAUTHORIZED, "not_signed_in", "Please sign in to continue."),
    WrongCredentials: (HTTPStatus.UNAUTHORIZED, "wrong_credentials", "Wrong username or password."),
    TooManyAttempts: (
        HTTPStatus.TOO_MANY_REQUESTS,
        "too_many_attempts",
        "Too many attempts. Try again in a few minutes.",
    ),
    RateLimitExceeded: (
        HTTPStatus.TOO_MANY_REQUESTS,
        "rate_limited",
        "Too many requests. Please wait a moment and try again.",
    ),
    CaseNotFound: (HTTPStatus.NOT_FOUND, "case_not_found", "We couldn't find that case."),
    RunInProgress: (
        HTTPStatus.CONFLICT,
        "run_in_progress",
        "This case is being prepared right now.",
    ),
    CaseAlreadyDecided: (
        HTTPStatus.CONFLICT,
        "already_decided",
        "This case has already been decided.",
    ),
    FeeAlreadyRefunded: (HTTPStatus.CONFLICT, "already_refunded", ALREADY_REFUNDED_MESSAGE),
    NoFeeIdentified: (HTTPStatus.UNPROCESSABLE_ENTITY, "no_fee", NO_FEE_MESSAGE),
    RunLimitReached: (
        HTTPStatus.TOO_MANY_REQUESTS,
        "run_limit",
        "This case was prepared too many times in the last hour. Try again later.",
    ),
}
# Errors whose message is written for Luis by the service (BR-09 texts, design §4.3).
_ERRORS_WITH_MESSAGE: dict[type[Exception], tuple[int, str]] = {
    ApprovalNotAllowed: (HTTPStatus.FORBIDDEN, "needs_supervisor"),
    InvalidDecision: (HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_decision"),
}
_HTTP_ERRORS: dict[int, tuple[str, str]] = {
    HTTPStatus.NOT_FOUND: ("not_found", "We couldn't find what you were looking for."),
    HTTPStatus.METHOD_NOT_ALLOWED: ("method_not_allowed", "That action isn't available here."),
    HTTPStatus.REQUEST_ENTITY_TOO_LARGE: PAYLOAD_TOO_LARGE,
}
_OTHER_HTTP_ERROR = ("http_error", "Something went wrong. Please try again.")


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status_code)


def http_error_response(status_code: int) -> JSONResponse:
    code, message = _HTTP_ERRORS.get(status_code, _OTHER_HTTP_ERROR)
    return error_response(status_code, code, message)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        response = http_error_response(error.status_code)
        if error.headers:
            response.headers.update(error.headers)
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return error_response(HTTPStatus.UNPROCESSABLE_ENTITY, *VALIDATION_ERROR)

    for error_type, (status, code, message) in _DOMAIN_ERRORS.items():
        app.add_exception_handler(error_type, _fixed_message_handler(status, code, message))
    for error_type, (status, code) in _ERRORS_WITH_MESSAGE.items():
        app.add_exception_handler(error_type, _service_message_handler(status, code))


ErrorHandler = Callable[[Request, Exception], Awaitable[JSONResponse]]


def _fixed_message_handler(status: int, code: str, message: str) -> ErrorHandler:
    async def handler(request: Request, error: Exception) -> JSONResponse:
        return error_response(status, code, message)

    return handler


def _service_message_handler(status: int, code: str) -> ErrorHandler:
    async def handler(request: Request, error: Exception) -> JSONResponse:
        # ApprovalNotAllowed and InvalidDecision carry a message written for Luis.
        return error_response(status, code, getattr(error, "message", _OTHER_HTTP_ERROR[1]))

    return handler
