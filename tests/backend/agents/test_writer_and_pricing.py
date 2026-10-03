"""Reply writer request/response handling (design §7.1, §7.3) and pricing (design §9)."""

import json
from decimal import Decimal

import anthropic
import httpx2
import pytest

from app.agents.errors import ModelUnavailable
from app.agents.writer import ReplyFacts, Writer
from app.core.pricing import TokenUsage, UnknownModelPrice, cost_usd

FACTS = ReplyFacts(
    outcome="REFUND", first_name="Ana", credit_union_name="Riverbend Credit Union", language="en",
    tone="neutral", fee_name="overdraft fee", amount=Decimal("35.00"), fee_day="Mon, Sep 14",
    reason=None, member_message="My paycheck came the same day. <b>Can you refund this?</b>",
)  # fmt: skip


def reply(text: str, stop_reason: str = "end_turn") -> dict[str, object]:
    return {
        "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
        "content": [{"type": "text", "text": text}], "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 120, "output_tokens": 60, "cache_read_input_tokens": 700, "cache_creation_input_tokens": 0},
    }  # fmt: skip


def writer(payload: dict[str, object], seen: list[httpx2.Request]) -> Writer:
    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=payload)

    client = anthropic.AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    return Writer(client, model="claude-sonnet-5-5", timeout_seconds=30)


async def test_the_writer_returns_the_reply_with_usage_and_cost() -> None:
    written = await writer(reply("Hi Ana, we've refunded it."), []).write(FACTS)

    assert written.text == "Hi Ana, we've refunded it."
    assert written.usage == TokenUsage(input_tokens=120, output_tokens=60, cache_read_tokens=700)
    # 120 x $2 + 60 x $10 + 700 x $0.20, per million tokens
    assert written.cost_usd == Decimal("0.00098")


async def test_the_writer_request_is_cacheable_and_sonnet_5_5_safe() -> None:
    seen: list[httpx2.Request] = []

    await writer(reply("Hi Ana"), seen).write(FACTS)

    body = json.loads(seen[0].content)
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "temperature" not in body  # Sonnet 5.5 rejects non-default sampling
    assert body["thinking"] == {"type": "between_tools"}
    assert body["max_tokens"] == 400
    assert "Ana" not in body["system"][0]["text"]  # per-case data stays out of the cached prefix


async def test_member_text_reaches_the_writer_only_as_escaped_data() -> None:
    seen: list[httpx2.Request] = []

    await writer(reply("Hi Ana"), seen).write(FACTS)

    user = json.loads(seen[0].content)["messages"][0]["content"]
    assert "&lt;b&gt;Can you refund this?&lt;/b&gt;" in user
    assert user.count("<member_message>") == 1


@pytest.mark.parametrize(
    ("stop_reason", "reason"), [("refusal", "refusal"), ("max_tokens", "max_tokens")]
)
async def test_a_refused_or_cut_reply_is_unavailable_so_the_template_is_used(
    stop_reason: str, reason: str
) -> None:
    with pytest.raises(ModelUnavailable, match=reason):
        await writer(reply("partial", stop_reason), []).write(FACTS)


async def test_fault_injection_makes_the_writer_unavailable() -> None:
    client = anthropic.AsyncAnthropic(api_key="k")

    with pytest.raises(ModelUnavailable, match="fault_injection"):
        await Writer(client, model="claude-sonnet-5-5", timeout_seconds=30, down=True).write(FACTS)


def test_jev_bills_input_tokens_only() -> None:
    assert cost_usd(
        "jev-1.13.0", TokenUsage(input_tokens=1_000_000, output_tokens=5_000)
    ) == Decimal("0.042")


def test_an_unknown_model_has_no_guessed_price() -> None:
    with pytest.raises(UnknownModelPrice):
        cost_usd("gpt-imaginary", TokenUsage(input_tokens=1))
