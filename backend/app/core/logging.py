"""Structured JSON logs on stdout, one object per line (R-34).

Our code logs through structlog; stdlib loggers (uvicorn) go through the same JSON
renderer, so every line in the Railway log view has the same shape.
"""

import logging
import sys
import traceback
from typing import TextIO

import structlog
from structlog.typing import Processor

LOG_LEVEL = logging.INFO
HANDLER_NAME = "app-json"
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

_SHARED_PROCESSORS: list[Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
]


def configure_logging(stream: TextIO | None = None) -> None:
    """Idempotent: safe to call again (tests, the app factory, CLI entry points).

    Logs go to stdout (what Railway reads) unless a CLI passes stderr to keep stdout for
    its own report.
    """
    structlog.configure(
        processors=[*_SHARED_PROCESSORS, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if h.name != HANDLER_NAME]
    root.addHandler(_json_handler(stream or sys.stdout))
    root.setLevel(LOG_LEVEL)
    _route_uvicorn_through_root()


def error_trace(error: BaseException) -> dict[str, object]:
    """The type and the frames of an error, for an error log line.

    Never the message: an exception message can carry member data (no PII in logs).
    """
    frames = traceback.extract_tb(error.__traceback__)
    return {
        "error_type": type(error).__name__,
        "traceback": [f"{f.filename}:{f.lineno} in {f.name}: {f.line}" for f in frames],
    }


def _drop_terminal_colour_copy(
    _logger: object, _method: str, event_dict: structlog.typing.EventDict
) -> structlog.typing.EventDict:
    # uvicorn adds an ANSI-coloured duplicate of each message, meant for terminals.
    event_dict.pop("color_message", None)
    return event_dict


def _json_handler(stream: TextIO) -> logging.Handler:
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[
            *_SHARED_PROCESSORS,
            structlog.stdlib.ExtraAdder(),
            _drop_terminal_colour_copy,
        ],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
    )
    handler = logging.StreamHandler(stream)
    handler.set_name(HANDLER_NAME)
    handler.setFormatter(formatter)
    return handler


def _route_uvicorn_through_root() -> None:
    # uvicorn installs its own plain-text handlers before loading the app.
    for name in UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
