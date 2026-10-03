"""Builds the model clients from settings (CLAUDE.md "Models"; design §6, §7.1, §10)."""

import anthropic
import httpx

from app.agents.decider import FallbackDecider, HaikuDecider, JevDecider
from app.agents.writer import Writer
from app.core.config import Settings

ANTHROPIC_MAX_RETRIES = 3  # design §7.1; the SDK retries 408/409/429/5xx (incl. 529)


def active_fault(settings: Settings) -> str:
    """FAULT_INJECTION, which production always ignores (design §10)."""
    return "" if settings.is_production else settings.fault_injection


def anthropic_client(settings: Settings) -> anthropic.AsyncAnthropic:
    key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
    return anthropic.AsyncAnthropic(
        api_key=key, timeout=settings.anthropic_timeout_seconds, max_retries=ANTHROPIC_MAX_RETRIES
    )


def jev_http_client(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=settings.jev_base_url)


def build_decider(
    settings: Settings, http: httpx.AsyncClient, claude: anthropic.AsyncAnthropic
) -> FallbackDecider:
    fault = active_fault(settings)
    jev = JevDecider(
        http,
        api_key=settings.jev_api_key.get_secret_value() if settings.jev_api_key else "",
        model=settings.jev_model,
        timeout_seconds=settings.jev_timeout_seconds,
        down=fault == "jev_down",
    )
    haiku = HaikuDecider(
        claude, model=settings.anthropic_fast_model, down=fault == "anthropic_down"
    )
    return FallbackDecider(jev, haiku)


def build_writer(settings: Settings, claude: anthropic.AsyncAnthropic) -> Writer:
    return Writer(
        claude,
        model=settings.anthropic_writer_model,
        timeout_seconds=settings.anthropic_timeout_seconds,
        down=active_fault(settings) == "anthropic_down",
    )
