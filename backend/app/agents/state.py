"""What the flow knows as it runs (design §5.1). Nodes return partial updates of RunState."""

import uuid
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.agents.decider import Decisions
from app.rules.model import Evaluation, ReasonCode, TypedAnswer
from app.tools.schemas import (
    CaseContext,
    FeeCandidate,
    LedgerTransaction,
    MemberAccount,
    MemberStanding,
)

ReplyLanguage = Literal["en", "es"]


@dataclass(frozen=True)
class Exit:
    """An early end of the flow: manual review (with a BR-13 reason) or not a refund."""

    kind: Literal["manual", "not_refund"]
    reason: ReasonCode | None = None


@dataclass(frozen=True)
class Screening:
    intent: str
    intent_answer: TypedAnswer
    injection_probability: float
    language: ReplyLanguage  # "other" replies in English (design §6.1)
    language_answer: TypedAnswer
    tone: Literal["neutral", "friendly", "upset"]


@dataclass(frozen=True)
class PolicyQuote:
    passage_id: int
    document_slug: str
    document_title: str
    text: str  # verbatim passage, never generated (R-10, LLM09)


@dataclass(frozen=True)
class Draft:
    text: str
    source: Literal["writer", "template"]
    guard_failures: tuple[str, ...] = ()
    guard_decisions: Decisions | None = None


@dataclass(frozen=True)
class FinalOutcome:
    case_status: str
    recommendation: str
    reason_code: str
    tier: str
    refunded: bool
    proposal_id: int | None


class RunState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    case_id: int
    run_id: uuid.UUID
    case: CaseContext | None = None
    screening: Screening | None = None
    accounts: list[MemberAccount] = []
    candidates: list[FeeCandidate] = []
    refunds: list[LedgerTransaction] = []
    standing: MemberStanding | None = None
    fee: FeeCandidate | None = None
    fee_choice: TypedAnswer | None = None  # None: one candidate, identified deterministically
    day_postings: list[LedgerTransaction] = []
    evaluation: Evaluation | None = None
    policy_quote: PolicyQuote | None = None
    draft: Draft | None = None
    exit: Exit | None = None
    outcome: FinalOutcome | None = None
