"""Recorded model answers replay exactly, so CI runs the evals offline (seed-and-evals §3.2)."""

from decimal import Decimal

import pytest
from eval_fixtures import (
    FixtureMismatch,
    Recording,
    RecordingDecider,
    RecordingWriter,
    ReplayDecider,
    ReplayWriter,
)
from fakes import FakeWriter, ScriptedDecider

from app.agents.errors import ModelUnavailable
from app.agents.questions import screening_questions
from app.agents.writer import ReplyFacts

FACTS = ReplyFacts(
    outcome="REFUND", first_name="Ana", credit_union_name="Riverbend Credit Union", language="en",
    tone="neutral", fee_name="overdraft fee", amount=Decimal("35.00"), fee_day="Mon, Sep 14",
    reason=None, member_message="Member: My paycheck came the same day.",
)  # fmt: skip


async def test_recorded_decisions_and_replies_replay_the_same() -> None:
    recording = Recording()
    decider = RecordingDecider(ScriptedDecider(), recording)
    live = await decider.decide("Member: refund please", screening_questions())

    replayed = await ReplayDecider(recording).decide("anything", screening_questions())

    assert replayed.choice("intent") == live.choice("intent")
    assert replayed.cost_usd == live.cost_usd


async def test_a_recorded_outage_replays_as_an_outage() -> None:
    recording = Recording()
    with pytest.raises(ModelUnavailable):
        await RecordingDecider(ScriptedDecider(down=True), recording).decide(
            "x", screening_questions()
        )

    with pytest.raises(ModelUnavailable):
        await ReplayDecider(recording).decide("x", screening_questions())


async def test_asking_something_that_was_not_recorded_is_a_clear_error() -> None:
    with pytest.raises(FixtureMismatch):
        await ReplayDecider(Recording()).decide("x", screening_questions())


async def test_the_writer_replays_its_reply() -> None:
    recording = Recording()
    live = await RecordingWriter(FakeWriter(), recording).write(FACTS)

    replayed = await ReplayWriter(recording).write(FACTS)

    assert (replayed.text, replayed.cost_usd) == (live.text, live.cost_usd)
