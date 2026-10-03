"""Vocabulary and value types of the rules engine (business-rules.md). Pure: no I/O."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Literal, Self

from app.core.config import Settings


class FeeType(StrEnum):
    COURTESY_PAY = "COURTESY_PAY"
    NSF = "NSF"
    OUT_OF_NETWORK_ATM = "OUT_OF_NETWORK_ATM"
    EXCESS_WITHDRAWAL = "EXCESS_WITHDRAWAL"
    OTHER = "OTHER"


class Recommendation(StrEnum):
    REFUND = "REFUND"
    NO_REFUND = "NO_REFUND"
    MANUAL = "MANUAL"


class ReasonCode(StrEnum):
    # BR-07 outcomes
    ELIGIBLE = "ELIGIBLE"
    ALREADY_REFUNDED = "ALREADY_REFUNDED"
    FEE_TYPE_NOT_COVERED = "FEE_TYPE_NOT_COVERED"
    OUT_OF_WINDOW = "OUT_OF_WINDOW"
    NOT_GOOD_STANDING = "NOT_GOOD_STANDING"
    NO_QUALIFYING_REASON = "NO_QUALIFYING_REASON"
    LIMIT_REACHED = "LIMIT_REACHED"
    # BR-13 manual review reasons
    INJECTION_SUSPECTED = "INJECTION_SUSPECTED"
    INTENT_UNCLEAR = "INTENT_UNCLEAR"
    NO_FEE_FOUND = "NO_FEE_FOUND"
    AMBIGUOUS_FEE = "AMBIGUOUS_FEE"
    AI_UNAVAILABLE = "AI_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    REJECTED_BY_STAFF = "REJECTED_BY_STAFF"


class Tier(StrEnum):
    AUTO = "AUTO"
    STAFF = "STAFF"
    SUPERVISOR = "SUPERVISOR"
    MANUAL = "MANUAL"


class Role(StrEnum):
    STAFF = "staff"
    SUPERVISOR = "supervisor"
    SYSTEM = "system"


class Verdict(StrEnum):
    """BR-09: may this actor execute this refund?"""

    ALLOWED = "ALLOWED"
    NEEDS_SUPERVISOR = "NEEDS_SUPERVISOR"
    NEVER = "NEVER"
    NO_FEE = "NO_FEE"


@dataclass(frozen=True)
class Thresholds:
    """The business settings of business-rules.md, nothing else."""

    refund_limit_per_window: int
    refund_window_days: int
    claim_window_days: int
    staff_approval_limit: Decimal
    auto_refund_enabled: bool
    auto_refund_max_amount: Decimal
    auto_min_confidence: float
    auto_max_injection: float

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(
            refund_limit_per_window=settings.refund_limit_per_window,
            refund_window_days=settings.refund_window_days,
            claim_window_days=settings.claim_window_days,
            staff_approval_limit=settings.staff_approval_limit,
            auto_refund_enabled=settings.auto_refund_enabled,
            auto_refund_max_amount=settings.auto_refund_max_amount,
            auto_min_confidence=settings.auto_min_confidence,
            auto_max_injection=settings.auto_max_injection,
        )


@dataclass(frozen=True)
class LedgerEntry:
    id: int
    sub_account_id: int
    date: date
    description: str
    amount: Decimal
    balance_after: Decimal
    posting_ref: str


@dataclass(frozen=True)
class StandingFlag:
    flag: str
    resolved: bool


@dataclass(frozen=True)
class RuleInput:
    """Everything BR-01…BR-07 need for one fee, gathered by the read-only tools."""

    first_name: str
    as_of: date
    fee: LedgerEntry
    day_postings: tuple[LedgerEntry, ...]  # every transaction on the fee's sub-account that day
    refunds: tuple[LedgerEntry, ...]  # refund transactions across the member scope
    fee_has_refund_action: bool
    flags: tuple[StandingFlag, ...]


@dataclass(frozen=True)
class Check:
    rule: str
    ok: bool
    text: str
    warning: bool = False  # passed, but Luis should notice (e.g. last refund available)


@dataclass(frozen=True)
class Evaluation:
    recommendation: Recommendation
    reason_code: ReasonCode
    fee_type: FeeType
    amount: Decimal  # BR-10: abs(fee.amount), from the ledger
    refunds_in_window: int
    refunds_left_after: int
    checks: tuple[Check, ...]


@dataclass(frozen=True)
class TypedAnswer:
    source: Literal["jev", "fallback"]
    confidence: float


@dataclass(frozen=True)
class AutoSignals:
    """What the run knows that BR-08's AUTO conditions depend on."""

    typed_answers: tuple[TypedAnswer, ...]  # every typed decision of the run
    fee_choice: TypedAnswer | None  # None: a single candidate, identified deterministically
    injection_probability: float
    draft_source: Literal["writer", "template"]
    guard_passed: bool


@dataclass(frozen=True)
class TierDecision:
    tier: Tier
    auto_blockers: tuple[str, ...]  # which AUTO conditions failed (empty when AUTO)


@dataclass(frozen=True)
class AuthorityDecision:
    verdict: Verdict
    message: str | None  # plain text for Luis when the refund is refused
