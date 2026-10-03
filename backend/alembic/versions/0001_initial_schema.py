"""Initial schema: given tables, added tables, agent_ro grants, append-only audit log.

Design §3 (data model) and §3.3 (roles, R-31). Runs as app_rw, which owns the schema.

Revision ID: 0001
Revises:
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MONEY = sa.Numeric(12, 2)
USD_COST = sa.Numeric(12, 6)


def _now() -> sa.TextClause:
    return sa.text("now()")


def upgrade() -> None:
    _create_given_tables()
    _create_reference_tables()
    _create_case_tables()
    _create_policy_tables()
    _grant_agent_ro()
    _make_audit_log_append_only()


def _create_given_tables() -> None:
    """§3.1: columns exactly as in the PDF."""
    op.create_table(
        "credit_unions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("member_id", sa.Integer, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
        sa.CheckConstraint(
            "status IN ('waiting_for_bank', 'waiting_for_member', 'read_by_bank', 'closed')",
            name="conversation_status",
        ),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("conversation_id", sa.Integer, sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("author_id", sa.String(32), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
    )
    op.create_index(
        "ix_messages_conversation_created", "messages", ["conversation_id", "created_at"]
    )
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("member_id", sa.Integer, nullable=False),
        sa.Column("credit_union_id", sa.Integer, sa.ForeignKey("credit_unions.id"), nullable=False),
        sa.Column("account_number", sa.String(32), nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False),
    )
    op.create_index("ix_accounts_member_id", "accounts", ["member_id"])
    op.create_table(
        "sub_accounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("balance", MONEY, nullable=False),
        sa.Column("available", MONEY, nullable=False),
        sa.CheckConstraint("type IN ('SAVINGS', 'CHECKING', 'LOAN')", name="sub_account_type"),
    )
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sub_account_id", sa.Integer, sa.ForeignKey("sub_accounts.id"), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("balance_after", MONEY, nullable=False),
        sa.Column("posting_ref", sa.String(13), nullable=False),
        sa.UniqueConstraint("posting_ref", "sub_account_id", name="uq_transactions_posting_ref"),
        sa.CheckConstraint(r"posting_ref ~ '^\d{8}-\d{4}$'", name="posting_ref_format"),
    )
    op.create_index("ix_transactions_sub_account_date", "transactions", ["sub_account_id", "date"])


def _create_reference_tables() -> None:
    op.create_table(
        "member_profiles",
        sa.Column("member_id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("first_name", sa.Text, nullable=False),
        sa.Column("last_name", sa.Text, nullable=False),
    )
    op.create_table(
        "member_flags",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("member_id", sa.Integer, nullable=False),
        sa.Column("flag", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("flag IN ('PAST_FRAUD', 'DEBT_IN_COLLECTIONS')", name="member_flag"),
    )
    op.create_index("ix_member_flags_member_id", "member_flags", ["member_id"])
    op.create_table(
        "staff",
        sa.Column("id", sa.String(8), primary_key=True),
        sa.Column("first_name", sa.Text, nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("username", sa.String(64), unique=True),
        sa.Column("password_hash", sa.Text),
        sa.CheckConstraint("role IN ('staff', 'supervisor', 'system')", name="staff_role"),
    )


def _create_case_tables() -> None:
    op.create_table(
        "cases",
        sa.Column(
            "conversation_id",
            sa.Integer,
            sa.ForeignKey("conversations.id"),
            primary_key=True,
            autoincrement=False,
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("manual_reason_code", sa.String(32)),
        sa.Column("current_proposal_id", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.Column("version", sa.Integer, server_default="1", nullable=False),
        sa.CheckConstraint(
            "status IN ('new', 'running', 'ready', 'needs_supervisor', 'manual_review',"
            " 'not_refund', 'auto_resolved', 'resolved')",
            name="case_status",
        ),
        sa.CheckConstraint("category IN ('fee_refund', 'other', 'unknown')", name="case_category"),
    )
    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", sa.Integer, sa.ForeignKey("cases.conversation_id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(32)),
        sa.Column("total_cost_usd", USD_COST, server_default="0", nullable=False),
        sa.Column("total_latency_ms", sa.Integer, server_default="0", nullable=False),
        sa.Column("request_id", sa.String(128)),
        sa.CheckConstraint("status IN ('running', 'completed', 'failed')", name="run_status"),
    )
    op.create_index("ix_agent_runs_case_id", "agent_runs", ["case_id"])
    op.create_table(
        "agent_steps",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id"), nullable=False
        ),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("cost_usd", USD_COST),
        sa.Column("used_fallback", sa.Boolean, server_default="false", nullable=False),
        sa.Column("error_code", sa.String(32)),
        sa.Column("output", postgresql.JSONB),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_agent_steps_run_ordinal"),
        sa.CheckConstraint(
            "kind IN ('decision', 'tool', 'rules', 'retrieval', 'writer', 'guard')",
            name="step_kind",
        ),
        sa.CheckConstraint("provider IN ('jev', 'anthropic', 'db', 'none')", name="step_provider"),
        sa.CheckConstraint("status IN ('running', 'done', 'failed')", name="step_status"),
    )
    op.create_table(
        "proposals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("case_id", sa.Integer, sa.ForeignKey("cases.conversation_id"), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.id")),
        sa.Column("recommendation", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column("tier", sa.String(32), nullable=False),
        sa.Column("fee_transaction_id", sa.Integer, sa.ForeignKey("transactions.id")),
        sa.Column("amount", MONEY),
        sa.Column("checks", postgresql.JSONB),
        sa.Column("evidence", postgresql.JSONB),
        sa.Column("policy_quote", postgresql.JSONB),
        sa.Column("language", sa.String(8)),
        sa.Column("tone", sa.String(16)),
        sa.Column("draft_reply", sa.Text),
        sa.Column("draft_source", sa.String(32)),
        sa.Column("decisions", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.CheckConstraint(
            "recommendation IN ('REFUND', 'NO_REFUND', 'MANUAL')", name="recommendation"
        ),
        sa.CheckConstraint("tier IN ('AUTO', 'STAFF', 'SUPERVISOR', 'MANUAL')", name="tier"),
        sa.CheckConstraint("draft_source IN ('writer', 'template')", name="draft_source"),
    )
    op.create_index("ix_proposals_case_id", "proposals", ["case_id"])
    # cases <-> proposals is circular, so this constraint comes after both tables.
    op.create_foreign_key(
        "fk_cases_current_proposal", "cases", "proposals", ["current_proposal_id"], ["id"]
    )
    op.create_table(
        "decisions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("case_id", sa.Integer, sa.ForeignKey("cases.conversation_id"), nullable=False),
        sa.Column("proposal_id", sa.Integer, sa.ForeignKey("proposals.id")),
        sa.Column("actor_id", sa.String(8), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("reply_text", sa.Text),
        sa.Column("reason", sa.Text),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("response", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        # R-15: the same Idempotency-Key on the same case is the same decision.
        sa.UniqueConstraint("case_id", "idempotency_key", name="uq_decisions_idempotency"),
        sa.CheckConstraint("action IN ('approve', 'edit', 'reject')", name="decision_action"),
        sa.CheckConstraint("outcome IN ('refund', 'no_refund', 'none')", name="decision_outcome"),
    )
    op.create_table(
        "refund_actions",
        sa.Column("id", sa.Integer, primary_key=True),
        # BR-11 / R-15: one refund per case and per fee, enforced by the database.
        sa.Column(
            "case_id",
            sa.Integer,
            sa.ForeignKey("cases.conversation_id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "fee_transaction_id",
            sa.Integer,
            sa.ForeignKey("transactions.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "refund_transaction_id", sa.Integer, sa.ForeignKey("transactions.id"), nullable=False
        ),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("actor_id", sa.String(8), sa.ForeignKey("staff.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="amount_positive"),
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.Column("actor_id", sa.String(8)),
        sa.Column("case_id", sa.Integer),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("details", postgresql.JSONB, server_default="{}", nullable=False),
    )
    op.create_index("ix_audit_log_case_id", "audit_log", ["case_id"])
    op.create_table(
        "feedback_evals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("case_id", sa.Integer, sa.ForeignKey("cases.conversation_id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_now(), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
    )


def _create_policy_tables() -> None:
    op.create_table(
        "policy_documents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
    )
    op.create_table(
        "policy_passages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("document_id", sa.Integer, sa.ForeignKey("policy_documents.id"), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR,
            sa.Computed("to_tsvector('english', text)", persisted=True),
            nullable=False,
        ),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_policy_passages_ordinal"),
    )
    op.create_index("ix_policy_passages_tsv", "policy_passages", ["tsv"], postgresql_using="gin")


def _grant_agent_ro() -> None:
    # design §3.3: what the agent tools may read. Nothing else, and never write.
    op.execute(
        """
        GRANT SELECT ON
            conversations, messages, accounts, sub_accounts, transactions,
            credit_unions, member_profiles, member_flags, refund_actions,
            policy_documents, policy_passages
        TO agent_ro
        """
    )
    # Tables created later by app_rw are not granted to anyone unless a migration says so.
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM PUBLIC")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM agent_ro")


def _make_audit_log_append_only() -> None:
    # R-35 / OWASP A09: who-did-what can be added, never rewritten. TRUNCATE (demo reset,
    # local only) is still possible for the owner.
    op.execute(
        """
        CREATE FUNCTION audit_log_reject_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only';
        END
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_append_only
        BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_reject_change()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_reject_change()")
    op.drop_constraint("fk_cases_current_proposal", "cases", type_="foreignkey")
    for table in (
        "feedback_evals",
        "audit_log",
        "refund_actions",
        "decisions",
        "proposals",
        "agent_steps",
        "agent_runs",
        "cases",
        "policy_passages",
        "policy_documents",
        "staff",
        "member_flags",
        "member_profiles",
        "transactions",
        "sub_accounts",
        "accounts",
        "messages",
        "conversations",
        "credit_unions",
    ):
        op.drop_table(table)
