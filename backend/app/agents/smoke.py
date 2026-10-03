"""One tiny real call to each model (tasks P4, `make smoke-models`). Paid: well under $0.05.

Checks the keys, the Jev contract, the Haiku fallback, and that the writer's system
prompt is long enough to be cached (the second writer call must read from the cache).
Uses an invented member message: no real data.
"""

import asyncio
from decimal import Decimal

import structlog

from app.agents.clients import anthropic_client, build_writer, jev_http_client
from app.agents.decider import HaikuDecider, JevDecider
from app.agents.questions import screening_questions
from app.agents.writer import SYSTEM_PROMPT, ReplyFacts
from app.core.config import Settings
from app.core.logging import configure_logging

MESSAGE = "Member: Hi, I got an overdraft fee but my paycheck came the same day. Can you refund it?"
MIN_CACHEABLE_TOKENS = 512  # Claude Sonnet 5.5, prompt caching docs (checked 2026-10-03)
SAMPLE = ReplyFacts(
    outcome="REFUND", first_name="Sam", credit_union_name="Example Credit Union", language="en",
    tone="neutral", fee_name="overdraft fee", amount=Decimal("35.00"), fee_day="Mon, Sep 14",
    reason=None, member_message=MESSAGE,
)  # fmt: skip

log = structlog.get_logger(__name__)


async def _main() -> None:
    configure_logging()
    settings = Settings()
    claude = anthropic_client(settings)
    questions = screening_questions()
    async with jev_http_client(settings) as http:
        jev_key = settings.jev_api_key.get_secret_value() if settings.jev_api_key else ""
        jev = JevDecider(
            http,
            api_key=jev_key,
            model=settings.jev_model,
            timeout_seconds=settings.jev_timeout_seconds,
        )
        answer = await jev.decide(MESSAGE, questions)
        log.info(
            "smoke_jev",
            model=answer.model,
            intent=answer.choice("intent").choice,
            cost_usd=str(answer.cost_usd),
            latency_ms=answer.latency_ms,
            request_id=answer.request_id,
        )
    haiku = await HaikuDecider(claude, model=settings.anthropic_fast_model).decide(
        MESSAGE, questions
    )
    log.info(
        "smoke_haiku",
        model=haiku.model,
        intent=haiku.choice("intent").choice,
        cost_usd=str(haiku.cost_usd),
        latency_ms=haiku.latency_ms,
    )
    counted = await claude.messages.count_tokens(
        model=settings.anthropic_writer_model,
        system=[{"type": "text", "text": SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": "."}],
    )
    log.info(
        "smoke_writer_prompt",
        system_tokens_about=counted.input_tokens,
        cacheable_minimum=MIN_CACHEABLE_TOKENS,
    )
    writer = build_writer(settings, claude)
    for attempt in ("first", "second"):
        reply = await writer.write(SAMPLE)
        log.info(
            "smoke_writer", attempt=attempt, model=reply.model, cost_usd=str(reply.cost_usd),
            latency_ms=reply.latency_ms, words=len(reply.text.split()),
            cache_write_tokens=reply.usage.cache_write_tokens, cache_read_tokens=reply.usage.cache_read_tokens,
        )  # fmt: skip


if __name__ == "__main__":
    asyncio.run(_main())
