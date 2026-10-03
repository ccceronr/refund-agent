"""The one place that maps errors to the API shape {"error": {"code", "message"}} (R-21).

Messages are plain language for the UI (ui.md §3): never exception text, codes from
other systems, or stack traces.
"""

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

INTERNAL_ERROR = ("internal_error", "Something went wrong on our side. Please try again.")
VALIDATION_ERROR = ("validation_error", "Some of the information sent isn't valid.")
PAYLOAD_TOO_LARGE = ("payload_too_large", "That's more data than we accept in one request.")
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
