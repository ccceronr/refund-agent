"""What the read-only tools return. Money is Decimal, straight from the ledger (BR-10)."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ToolModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class MemberMessage(ToolModel):
    body: str
    sent_at: datetime


class CaseContext(ToolModel):
    conversation_id: int
    member_id: int
    first_name: str
    last_name: str
    credit_union_name: str
    subject: str
    member_messages: list[MemberMessage]
    # business-rules.md: the latest member-authored message; every date rule uses it.
    as_of: datetime


class SubAccountInfo(ToolModel):
    id: int
    type: str
    name: str
    balance: Decimal
    available: Decimal


class MemberAccount(ToolModel):
    id: int
    account_number: str
    is_primary: bool
    sub_accounts: list[SubAccountInfo]


class LedgerTransaction(ToolModel):
    id: int
    sub_account_id: int
    sub_account_name: str
    date: date
    description: str
    amount: Decimal
    balance_after: Decimal
    posting_ref: str


class FeeCandidate(ToolModel):
    transaction: LedgerTransaction
    # BR-05: a refund_actions row means the fee was already refunded through this app.
    has_refund_action: bool


class StandingFlag(ToolModel):
    flag: str
    created_at: datetime
    resolved_at: datetime | None


class MemberStanding(ToolModel):
    flags: list[StandingFlag]


class PolicyHit(ToolModel):
    passage_id: int
    document_slug: str
    document_title: str
    text: str
    rank: float
