"""SQLAlchemy models (design §3). Money is NUMERIC(12,2) and Python Decimal, never float.

The given tables (§3.1) keep exactly the PDF's columns, with naive timestamps as given.
Added tables (§3.2) use timezone-aware timestamps.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

MONEY = Numeric(12, 2)
USD_COST = Numeric(12, 6)

CONVERSATION_STATUSES = ("waiting_for_bank", "waiting_for_member", "read_by_bank", "closed")
SUB_ACCOUNT_TYPES = ("SAVINGS", "CHECKING", "LOAN")
MEMBER_FLAGS = ("PAST_FRAUD", "DEBT_IN_COLLECTIONS")
STAFF_ROLES = ("staff", "supervisor", "system")
CASE_STATUSES = (
    "new",
    "running",
    "ready",
    "needs_supervisor",
    "manual_review",
    "not_refund",
    "auto_resolved",
    "resolved",
)
CASE_CATEGORIES = ("fee_refund", "other", "unknown")
RUN_STATUSES = ("running", "completed", "failed")
STEP_KINDS = ("decision", "tool", "rules", "retrieval", "writer", "guard")
STEP_PROVIDERS = ("jev", "anthropic", "db", "none")
STEP_STATUSES = ("running", "done", "failed")
RECOMMENDATIONS = ("REFUND", "NO_REFUND", "MANUAL")
TIERS = ("AUTO", "STAFF", "SUPERVISOR", "MANUAL")
DRAFT_SOURCES = ("writer", "template")
DECISION_ACTIONS = ("approve", "edit", "reject")
DECISION_OUTCOMES = ("refund", "no_refund", "none")


def choice(name: str, values: tuple[str, ...]) -> Enum:
    """A text column restricted to `values` by a CHECK constraint (no Postgres ENUM type,
    so adding a value later is a plain migration)."""
    return Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def created_now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {Decimal: MONEY, dict[str, Any]: JSONB}


# --- Given tables (§3.1): columns exactly as in the PDF -------------------------------


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int]
    subject: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(choice("conversation_status", CONVERSATION_STATUSES))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    # A member id, or a staff id starting with "S" (not a foreign key, per the PDF).
    author_id: Mapped[str] = mapped_column(String(32))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False))


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (Index("ix_accounts_member_id", "member_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int]
    credit_union_id: Mapped[int] = mapped_column(ForeignKey("credit_unions.id"))
    account_number: Mapped[str] = mapped_column(String(32))
    is_primary: Mapped[bool]


class SubAccount(Base):
    __tablename__ = "sub_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    type: Mapped[str] = mapped_column(choice("sub_account_type", SUB_ACCOUNT_TYPES))
    name: Mapped[str] = mapped_column(Text)
    balance: Mapped[Decimal]
    available: Mapped[Decimal]


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_transactions_sub_account_date", "sub_account_id", "date"),
        UniqueConstraint("posting_ref", "sub_account_id", name="uq_transactions_posting_ref"),
        CheckConstraint(r"posting_ref ~ '^\d{8}-\d{4}$'", name="posting_ref_format"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sub_account_id: Mapped[int] = mapped_column(ForeignKey("sub_accounts.id"))
    date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal]
    balance_after: Mapped[Decimal]
    posting_ref: Mapped[str] = mapped_column(String(13))


# --- Added tables (§3.2) -------------------------------------------------------------


class CreditUnion(Base):
    __tablename__ = "credit_unions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text)


class MemberProfile(Base):
    __tablename__ = "member_profiles"

    member_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str] = mapped_column(Text)


class MemberFlag(Base):
    __tablename__ = "member_flags"
    __table_args__ = (Index("ix_member_flags_member_id", "member_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int]
    flag: Mapped[str] = mapped_column(choice("member_flag", MEMBER_FLAGS))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Staff(Base):
    __tablename__ = "staff"
    id: Mapped[str] = mapped_column(String(8), primary_key=True)
    first_name: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(choice("staff_role", STAFF_ROLES))
    username: Mapped[str | None] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)


class Case(Base):
    __tablename__ = "cases"
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), primary_key=True, autoincrement=False
    )
    status: Mapped[str] = mapped_column(choice("case_status", CASE_STATUSES))
    category: Mapped[str] = mapped_column(choice("case_category", CASE_CATEGORIES))
    manual_reason_code: Mapped[str | None] = mapped_column(String(32))
    # Circular with proposals.case_id, so the constraint is added after both tables exist.
    current_proposal_id: Mapped[int | None] = mapped_column(
        ForeignKey("proposals.id", use_alter=True, name="fk_cases_current_proposal")
    )
    created_at: Mapped[datetime] = created_now()
    updated_at: Mapped[datetime] = created_now()
    # Optimistic concurrency for decisions (design §4.3).
    version: Mapped[int] = mapped_column(Integer, server_default="1")


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_case_id", "case_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.conversation_id"))
    status: Mapped[str] = mapped_column(choice("run_status", RUN_STATUSES))
    started_at: Mapped[datetime] = created_now()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(32))
    total_cost_usd: Mapped[Decimal] = mapped_column(USD_COST, server_default="0")
    total_latency_ms: Mapped[int] = mapped_column(Integer, server_default="0")
    request_id: Mapped[str | None] = mapped_column(String(128))


class AgentStep(Base):
    __tablename__ = "agent_steps"
    __table_args__ = (UniqueConstraint("run_id", "ordinal", name="uq_agent_steps_run_ordinal"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.id"))
    ordinal: Mapped[int]
    name: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(choice("step_kind", STEP_KINDS))
    provider: Mapped[str] = mapped_column(choice("step_provider", STEP_PROVIDERS))
    model: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(choice("step_status", STEP_STATUSES))
    latency_ms: Mapped[int | None]
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    cost_usd: Mapped[Decimal | None] = mapped_column(USD_COST)
    used_fallback: Mapped[bool] = mapped_column(server_default="false")
    error_code: Mapped[str | None] = mapped_column(String(32))
    output: Mapped[dict[str, Any] | None]
    started_at: Mapped[datetime] = created_now()


class Proposal(Base):
    __tablename__ = "proposals"
    __table_args__ = (Index("ix_proposals_case_id", "case_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.conversation_id"))
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    recommendation: Mapped[str] = mapped_column(choice("recommendation", RECOMMENDATIONS))
    reason_code: Mapped[str] = mapped_column(String(32))
    tier: Mapped[str] = mapped_column(choice("tier", TIERS))
    fee_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("transactions.id"))
    amount: Mapped[Decimal | None]
    checks: Mapped[dict[str, Any] | None]
    evidence: Mapped[dict[str, Any] | None]
    policy_quote: Mapped[dict[str, Any] | None]
    language: Mapped[str | None] = mapped_column(String(8))
    tone: Mapped[str | None] = mapped_column(String(16))
    draft_reply: Mapped[str | None] = mapped_column(Text)
    draft_source: Mapped[str | None] = mapped_column(choice("draft_source", DRAFT_SOURCES))
    decisions: Mapped[dict[str, Any] | None]
    created_at: Mapped[datetime] = created_now()


class Decision(Base):
    __tablename__ = "decisions"
    __table_args__ = (
        # R-15: the same Idempotency-Key on the same case is the same decision.
        UniqueConstraint("case_id", "idempotency_key", name="uq_decisions_idempotency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.conversation_id"))
    proposal_id: Mapped[int | None] = mapped_column(ForeignKey("proposals.id"))
    actor_id: Mapped[str] = mapped_column(ForeignKey("staff.id"))
    action: Mapped[str] = mapped_column(choice("decision_action", DECISION_ACTIONS))
    outcome: Mapped[str] = mapped_column(choice("decision_outcome", DECISION_OUTCOMES))
    reply_text: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    response: Mapped[dict[str, Any] | None]
    created_at: Mapped[datetime] = created_now()


class RefundAction(Base):
    """One explicit refund (BR-11). The unique constraints make a double refund impossible
    at the database level, whatever the code does (R-15, BR-05)."""

    __tablename__ = "refund_actions"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.conversation_id"), unique=True)
    fee_transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), unique=True)
    refund_transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"))
    amount: Mapped[Decimal]
    actor_id: Mapped[str] = mapped_column(ForeignKey("staff.id"))
    created_at: Mapped[datetime] = created_now()


class AuditLog(Base):
    """Append-only (R-35): the migration adds a trigger that rejects UPDATE and DELETE."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_case_id", "case_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    at: Mapped[datetime] = created_now()
    # Null for events with no known staff member (e.g. a failed login).
    actor_id: Mapped[str | None] = mapped_column(String(8))
    case_id: Mapped[int | None]
    event: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(server_default="{}")


class PolicyDocument(Base):
    __tablename__ = "policy_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)


class PolicyPassage(Base):
    __tablename__ = "policy_passages"
    __table_args__ = (
        Index("ix_policy_passages_tsv", "tsv", postgresql_using="gin"),
        UniqueConstraint("document_id", "ordinal", name="uq_policy_passages_ordinal"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("policy_documents.id"))
    ordinal: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', text)", persisted=True)
    )


class FeedbackEval(Base):
    __tablename__ = "feedback_evals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.conversation_id"))
    created_at: Mapped[datetime] = created_now()
    payload: Mapped[dict[str, Any]]
