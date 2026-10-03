"""What the API returns for the queue and the case page (design §4.1, §4.2).

Money and amounts are strings ("35.00"), never floats. No internal ids are shown to Luis;
the ids here are only what the UI sends back (the case, a fee Luis picks).
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class View(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)


class CaseListItem(View):
    id: int
    member_name: str
    topic: str
    status: str
    status_label: str
    received_at: datetime
    tier: str | None


class MemberView(View):
    name: str
    standing: Literal["good", "not_good"]
    credit_union: str


class MessageView(View):
    sender: Literal["member", "staff"] = Field(serialization_alias="from")
    author_name: str
    body: str
    sent_at: datetime


class CheckView(View):
    rule: str
    ok: bool
    text: str
    warning: bool


class PolicyQuoteView(View):
    document: str
    text: str


class FeeChoiceView(View):
    """BR-09 "Manual cases": a fee Luis may pick on an AMBIGUOUS_FEE case (shown without id)."""

    id: int
    label: str


class ProposalView(View):
    recommendation: str
    reason_code: str
    tier: str
    headline: str
    authority_note: str | None
    amount: str | None
    checks: list[CheckView]
    policy_quote: PolicyQuoteView | None
    draft_reply: str | None
    draft_source: str | None
    language: str | None
    manual_reason: str | None
    fee_choices: list[FeeChoiceView]


class FeeView(View):
    label: str
    amount: str
    date: date
    account: str
    account_number_full: str | None  # R-33: the only place the full number appears


class PostingView(View):
    order: int
    description: str
    raw_description: str
    amount: str
    balance_after: str
    is_fee: bool


class RefundView(View):
    date: date
    label: str
    amount: str


class EvidenceView(View):
    fee: FeeView | None
    day_postings: list[PostingView]
    refund_history: list[RefundView]
    refunds_used: int | None
    refunds_limit: int


class StepView(View):
    label: str
    status: str
    duration_ms: int | None


class RunView(View):
    status: str
    duration_ms: int
    cost_usd: str
    steps: list[StepView]


class DecisionView(View):
    action: str
    outcome: str
    by: str
    at: datetime


class CaseDetail(View):
    id: int
    status: str
    status_label: str
    topic: str
    received_at: datetime
    member: MemberView
    messages: list[MessageView]
    proposal: ProposalView | None
    evidence: EvidenceView | None
    run: RunView | None
    decision: DecisionView | None
