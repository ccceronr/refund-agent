"""Fake models for flow and API tests: answer like Jev and the writer would, from a script.

No test calls a real model (CLAUDE.md: real calls only with Camila's approval).
"""

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from app.agents.decider import Decisions, State
from app.agents.errors import ModelUnavailable
from app.agents.questions import ChoiceAnswer, NoulAnswer, Question
from app.agents.writer import ReplyFacts, WrittenReply
from app.core.pricing import TokenUsage
from app.rules.texts import money

DENIAL_WORDS = ("can't", "cannot", "no podemos")


class ScriptedDecider:
    """Answers like Jev would, from a script. Records which question sets it was asked."""

    def __init__(self, *, intent: str = "fee_refund", intent_confidence: float = 0.99, injection: float = 0.01,
                 language: str = "en", fee: str = "fee_1", fee_confidence: float = 0.97,
                 source: str = "jev", down: bool = False) -> None:  # fmt: skip
        self.script = {"intent": intent, "intent_confidence": intent_confidence, "injection": injection, "language": language, "fee": fee, "fee_confidence": fee_confidence}  # fmt: skip
        self.source = source
        self.down = down
        self.asked: list[frozenset[str]] = []
        self.states: list[State] = []

    async def decide(self, state: State, questions: Mapping[str, Question]) -> Decisions:
        self.asked.append(frozenset(questions))
        self.states.append(state)
        if self.down:
            raise ModelUnavailable("jev", "http_529")
        s = self.script
        if "intent" in questions:
            answers: dict[str, Any] = {
                "intent": ChoiceAnswer(choice=s["intent"], confidence=s["intent_confidence"]),
                "injection": NoulAnswer(noul=s["injection"]),
                "language": ChoiceAnswer(choice=s["language"], confidence=0.99),
                "tone": ChoiceAnswer(choice="neutral", confidence=0.7),
            }
        elif "fee" in questions:
            answers = {"fee": ChoiceAnswer(choice=s["fee"], confidence=s["fee_confidence"])}
        elif "passage" in questions:
            answers = {"passage": ChoiceAnswer(choice="p1", confidence=0.9)}
        else:  # the guard's language and outcome checks
            denied = any(word in str(state).lower() for word in DENIAL_WORDS)
            outcome = "refund_denied" if denied else "refund_confirmed"
            answers = {
                "language": NoulAnswer(noul=0.99),
                "outcome": ChoiceAnswer(choice=outcome, confidence=0.98),
            }
        return Decisions(
            answers,
            self.source,
            "jev-1.13.0",
            TokenUsage(input_tokens=100),
            Decimal("0.0000042"),
            3,
        )  # type: ignore[arg-type]


class FakeWriter:
    def __init__(self, *, fail: bool = False, text: str | None = None) -> None:
        self.fail, self.text, self.calls = fail, text, 0

    async def write(self, facts: ReplyFacts) -> WrittenReply:
        self.calls += 1
        if self.fail:
            raise ModelUnavailable("anthropic", "http_529")
        amount, signature = money(facts.amount), f"{facts.credit_union_name} Member Support"
        if facts.outcome == "REFUND":
            body = f"Hi {facts.first_name},\n\nWe've refunded the {amount} {facts.fee_name}. The money is back in your account today.\n\n{signature}"
        else:
            body = f"Hi {facts.first_name},\n\nWe can't refund the {amount} {facts.fee_name}. {facts.reason} Is there anything else we can help with?\n\n{signature}"
        usage = TokenUsage(input_tokens=50, output_tokens=40, cache_read_tokens=600)
        return WrittenReply(self.text or body, "claude-sonnet-5-5", usage, Decimal("0.0005"), 12)
