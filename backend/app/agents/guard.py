"""Output guard: a draft is saved only if it passes every check (design §7.5, R-12, LLM05).

Deterministic checks run first; the two model checks (language, outcome) go to the
decider in one request only when those pass. Any failure means the template is used.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.agents.decider import Decider, Decisions
from app.agents.errors import ModelUnavailable
from app.agents.questions import guard_questions
from app.agents.templates import Language
from app.rules.model import Recommendation

MAX_WORDS = 120
BANNED_WORDS = ("courtesy pay", "posting", "ledger", "tier", "core", "system prompt")
# Whole words (so "tierra" or "score" pass), plural included; "BR-" codes anywhere.
_BANNED = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in BANNED_WORDS) + r")s?\b|\bBR-", re.IGNORECASE
)
_LONG_DIGIT_RUN = re.compile(r"\d{5,}")  # IDs, account numbers
_DOLLAR_AMOUNT = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)")
_LANGUAGE_NAMES = {"en": "English", "es": "Spanish"}
_EXPECTED_OUTCOME = {
    Recommendation.REFUND: "refund_confirmed",
    Recommendation.NO_REFUND: "refund_denied",
}


@dataclass(frozen=True)
class GuardResult:
    passed: bool
    failures: tuple[str, ...]
    decisions: Decisions | None = None  # the model check, for cost and step logging


def deterministic_failures(draft: str, fee_amount: Decimal) -> list[str]:
    failures = []
    if any(amount not in (fee_amount, Decimal(0)) for amount in _dollar_amounts(draft)):
        failures.append("amount")
    if _BANNED.search(draft):
        failures.append("internal_term")
    if _LONG_DIGIT_RUN.search(draft):
        failures.append("digit_run")
    if len(draft.split()) > MAX_WORDS:
        failures.append("too_long")
    return failures


async def check_draft(
    draft: str,
    *,
    fee_amount: Decimal,
    language: Language,
    recommendation: Recommendation,
    decider: Decider,
    min_confidence: float,
) -> GuardResult:
    failures = deterministic_failures(draft, fee_amount)
    if failures:
        return GuardResult(passed=False, failures=tuple(failures))
    try:
        decisions = await decider.decide(draft, guard_questions(_LANGUAGE_NAMES[language]))
    except ModelUnavailable:
        # Fail closed: an unchecked draft is never sent (OWASP A10).
        return GuardResult(passed=False, failures=("guard_unavailable",))
    failures = _model_failures(decisions, recommendation, min_confidence)
    return GuardResult(passed=not failures, failures=tuple(failures), decisions=decisions)


def _model_failures(
    decisions: Decisions, recommendation: Recommendation, min_confidence: float
) -> list[str]:
    failures = []
    if decisions.noul("language").noul < min_confidence:
        failures.append("language")
    outcome = decisions.choice("outcome")
    expected = _EXPECTED_OUTCOME.get(recommendation)
    if outcome.choice != expected or outcome.confidence < min_confidence:
        failures.append("outcome")
    return failures


def _dollar_amounts(draft: str) -> list[Decimal]:
    amounts = []
    for match in _DOLLAR_AMOUNT.finditer(draft):
        try:
            amounts.append(Decimal(match.group(1).replace(",", "").rstrip(".")))
        except InvalidOperation:
            amounts.append(Decimal(-1))  # unreadable amount: never matches the fee
    return amounts
