"""Cost per model call, from pricing.toml (design §9, R-17). Never guessed."""

import tomllib
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from pathlib import Path

PRICING_FILE = Path(__file__).with_name("pricing.toml")
PER_MILLION = Decimal(1_000_000)


class UnknownModelPrice(LookupError):
    pass


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass(frozen=True)
class Price:
    input: Decimal
    output: Decimal
    cache_read: Decimal
    cache_write: Decimal


@cache
def _prices() -> dict[str, Price]:
    raw = tomllib.loads(PRICING_FILE.read_text())["models"]
    return {name: Price(**{k: Decimal(v) for k, v in rates.items()}) for name, rates in raw.items()}


def cost_usd(model: str, usage: TokenUsage) -> Decimal:
    price = _prices().get(model)
    if price is None:
        raise UnknownModelPrice(f"no price for model {model!r} in {PRICING_FILE.name}")
    total = (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + usage.cache_read_tokens * price.cache_read
        + usage.cache_write_tokens * price.cache_write
    )
    return total / PER_MILLION
