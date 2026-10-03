"""Structured JSON logs, one object per line, for our code and for uvicorn (R-34)."""

import io
import json
import logging
from collections.abc import Iterator

import pytest
import structlog

from app.core.logging import configure_logging


@pytest.fixture
def log_output() -> Iterator[io.StringIO]:
    configure_logging()
    handler = next(
        h
        for h in logging.getLogger().handlers
        if isinstance(h, logging.StreamHandler)
        and isinstance(h.formatter, structlog.stdlib.ProcessorFormatter)
    )
    stream = io.StringIO()
    previous = handler.setStream(stream)
    try:
        yield stream
    finally:
        handler.setStream(previous)


def _last_line(stream: io.StringIO) -> dict[str, object]:
    return json.loads(stream.getvalue().strip().splitlines()[-1])


def test_app_logs_are_json_lines(log_output: io.StringIO) -> None:
    structlog.get_logger("app.test").info("case_prepared", case_id=5012)

    line = _last_line(log_output)
    assert line["event"] == "case_prepared"
    assert line["case_id"] == 5012
    assert line["level"] == "info"
    assert "timestamp" in line


def test_uvicorn_terminal_colour_copy_is_dropped(log_output: io.StringIO) -> None:
    # uvicorn adds a second, ANSI-coloured copy of each message for terminals.
    logging.getLogger("uvicorn.error").info(
        "Started server process", extra={"color_message": "Started \x1b[36mserver\x1b[0m"}
    )

    assert "color_message" not in _last_line(log_output)


def test_uvicorn_logs_are_json_lines_too(log_output: io.StringIO) -> None:
    logging.getLogger("uvicorn.error").info("Started server process")

    line = _last_line(log_output)
    assert line["event"] == "Started server process"
    assert line["level"] == "info"
