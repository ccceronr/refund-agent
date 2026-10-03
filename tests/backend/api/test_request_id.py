"""X-Request-ID in and out, bound to every log line of the request (design §4, R-34)."""

import re

import pytest
from httpx import AsyncClient

GENERATED_ID = re.compile(r"[0-9a-f]{32}")


async def test_a_request_id_is_generated_when_none_is_sent(client: AsyncClient) -> None:
    response = await client.get("/api/health")

    assert GENERATED_ID.fullmatch(response.headers["x-request-id"])


async def test_a_valid_incoming_request_id_is_echoed(client: AsyncClient) -> None:
    response = await client.get("/api/health", headers={"X-Request-ID": "trace-2026.10_02"})

    assert response.headers["x-request-id"] == "trace-2026.10_02"


@pytest.mark.parametrize("unsafe_id", ["has space", "x" * 129, "line\tbreak", 'quote"d'])
async def test_an_unsafe_incoming_request_id_is_replaced(
    client: AsyncClient, unsafe_id: str
) -> None:
    response = await client.get("/api/health", headers={"X-Request-ID": unsafe_id})

    assert GENERATED_ID.fullmatch(response.headers["x-request-id"])


async def test_the_request_log_line_carries_the_request_id(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    await client.get("/api/health", headers={"X-Request-ID": "trace-42"})

    request_logs = [
        record.msg
        for record in caplog.records
        if isinstance(record.msg, dict) and record.msg.get("event") == "request"
    ]
    assert request_logs[-1]["request_id"] == "trace-42"
    assert request_logs[-1]["status"] == 200
    assert request_logs[-1]["path"] == "/api/health"
