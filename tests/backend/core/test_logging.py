"""Structured JSON logs, one object per line, for our code and for uvicorn (R-34)."""

import io
import json
import logging
import sys

import pytest
import structlog

from app.core.logging import configure_logging, error_trace


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


def test_error_logs_carry_the_trace_but_never_the_message(log_output: io.StringIO) -> None:
    # Exception messages can carry member data (CLAUDE.md: no names or accounts in logs).
    member_data = "Ana Lopez ••4210"
    try:
        raise ValueError(member_data)
    except ValueError as error:
        structlog.get_logger("app.test").error("run_crashed", **error_trace(error))

    line = _last_line(log_output)
    assert line["error_type"] == "ValueError"
    assert "test_error_logs_carry_the_trace_but_never_the_message" in str(line["traceback"])
    assert "Ana" not in log_output.getvalue()
    assert "4210" not in log_output.getvalue()


def test_a_cli_can_send_its_logs_to_stderr_and_keep_stdout_for_its_report(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(sys.stderr)
    try:
        structlog.get_logger("app.test").info("case_prepared")
        captured = capsys.readouterr()
    finally:
        configure_logging()

    assert "case_prepared" in captured.err
    assert captured.out == ""


def test_logs_never_carry_message_bodies_or_account_numbers(log_output: io.StringIO) -> None:
    # R-33, design §8: risky keys are dropped and long digit runs are redacted.
    structlog.get_logger("app.test").info(
        "reply_sent", body="Hi Ana", account_number="884210", note="paid from 884210", case_id=5012
    )

    line = _last_line(log_output)
    assert "body" not in line
    assert "account_number" not in line
    assert line["note"] == "paid from ••"
    assert line["case_id"] == 5012
    assert "884210" not in log_output.getvalue()
