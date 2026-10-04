"""Record real model answers once (--record) and replay them offline (--offline), so CI
can run the evals without API keys (seed-and-evals §3.2). One file per eval case."""

import json
from collections.abc import Mapping
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from app.agents.decider import Decider, Decisions, State
from app.agents.errors import ModelUnavailable
from app.agents.graph import ReplyWriter
from app.agents.questions import Answer, Question
from app.agents.writer import ReplyFacts, WrittenReply
from app.core.pricing import TokenUsage

FIXTURES = Path(__file__).parent / "fixtures"
_ANSWER = TypeAdapter(Answer)


class FixtureMismatch(RuntimeError):
    """The flow asked something the recording doesn't have: record the fixtures again."""


class Recording:
    def __init__(self) -> None:
        self.decider: list[dict[str, Any]] = []
        self.writer: list[dict[str, Any]] = []

    def save(self, case_id: str) -> None:
        FIXTURES.mkdir(exist_ok=True)
        body = {"decider": self.decider, "writer": self.writer}
        (FIXTURES / f"{case_id}.json").write_text(
            json.dumps(body, indent=2, ensure_ascii=False) + "\n"
        )

    @classmethod
    def load(cls, case_id: str) -> "Recording":
        path = FIXTURES / f"{case_id}.json"
        if not path.exists():
            raise FixtureMismatch(f"no fixture for {case_id}: run with --record first")
        body = json.loads(path.read_text())
        recording = cls()
        recording.decider, recording.writer = body["decider"], body["writer"]
        return recording


class RecordingDecider:
    def __init__(self, inner: Decider, recording: Recording) -> None:
        self._inner, self._recording = inner, recording

    async def decide(self, state: State, questions: Mapping[str, Question]) -> Decisions:
        entry: dict[str, Any] = {"questions": sorted(questions)}
        try:
            decisions = await self._inner.decide(state, questions)
        except ModelUnavailable as error:
            self._recording.decider.append({**entry, "unavailable": [error.provider, error.reason]})
            raise
        self._recording.decider.append({**entry, "decisions": _dump_decisions(decisions)})
        return decisions


class ReplayDecider:
    def __init__(self, recording: Recording) -> None:
        self._entries = iter(recording.decider)

    async def decide(self, state: State, questions: Mapping[str, Question]) -> Decisions:
        entry = next(self._entries, None)
        if entry is None or entry["questions"] != sorted(questions):
            raise FixtureMismatch(f"unexpected questions {sorted(questions)}")
        if "unavailable" in entry:
            raise ModelUnavailable(*entry["unavailable"])
        return _load_decisions(entry["decisions"])


class RecordingWriter:
    def __init__(self, inner: ReplyWriter, recording: Recording) -> None:
        self._inner, self._recording = inner, recording

    async def write(self, facts: ReplyFacts) -> WrittenReply:
        try:
            reply = await self._inner.write(facts)
        except ModelUnavailable as error:
            self._recording.writer.append({"unavailable": [error.provider, error.reason]})
            raise
        self._recording.writer.append({**asdict(reply), "cost_usd": str(reply.cost_usd)})
        return reply


class ReplayWriter:
    def __init__(self, recording: Recording) -> None:
        self._entries = iter(recording.writer)

    async def write(self, facts: ReplyFacts) -> WrittenReply:
        entry = next(self._entries, None)
        if entry is None:
            raise FixtureMismatch("the writer was not called when this fixture was recorded")
        if "unavailable" in entry:
            raise ModelUnavailable(*entry["unavailable"])
        return WrittenReply(
            text=entry["text"],
            model=entry["model"],
            usage=TokenUsage(**entry["usage"]),
            cost_usd=Decimal(entry["cost_usd"]),
            latency_ms=entry["latency_ms"],
        )


def _dump_decisions(decisions: Decisions) -> dict[str, Any]:
    return {
        "answers": {key: answer.model_dump() for key, answer in decisions.answers.items()},
        "source": decisions.source,
        "model": decisions.model,
        "usage": asdict(decisions.usage),
        "cost_usd": str(decisions.cost_usd),
        "latency_ms": decisions.latency_ms,
    }


def _load_decisions(data: dict[str, Any]) -> Decisions:
    return Decisions(
        answers={key: _ANSWER.validate_python(value) for key, value in data["answers"].items()},
        source=data["source"],
        model=data["model"],
        usage=TokenUsage(**data["usage"]),
        cost_usd=Decimal(data["cost_usd"]),
        latency_ms=data["latency_ms"],
    )
