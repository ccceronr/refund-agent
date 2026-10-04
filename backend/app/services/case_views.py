"""The queue and the case page (R-01, R-02, R-17; design §4.1, §4.2). Reads only."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Row, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.masking import mask_account
from app.db.models import (
    Account,
    AgentRun,
    AgentStep,
    Case,
    Conversation,
    CreditUnion,
    Decision,
    MemberFlag,
    MemberProfile,
    Message,
    Proposal,
    Staff,
)
from app.rules.checks import in_good_standing
from app.rules.model import ReasonCode, StandingFlag, Thresholds
from app.rules.texts import day, manual_reason_text, money
from app.services import labels
from app.services.auth import StaffMember
from app.services.errors import CaseNotFound
from app.services.view_models import (
    CaseDetail,
    CaseListItem,
    CheckView,
    DecisionView,
    EvidenceView,
    FeeChoiceView,
    FeeView,
    MemberView,
    MessageView,
    PolicyQuoteView,
    PostingView,
    ProposalView,
    RefundView,
    RunView,
    StepView,
)

type Record = Row[*tuple[Any, ...]]  # a result row of any shape
STAFF_ID_PREFIX = "S"  # messages.author_id: staff ids start with "S" (design §3.1)
DECIDED = ("resolved", "auto_resolved")


def _received_at() -> ColumnElement[datetime]:
    """When the member last wrote (what "oldest waiting first" sorts by)."""
    last_member_message = (
        select(func.max(Message.created_at))
        .where(
            Message.conversation_id == Conversation.id,
            Message.author_id.not_like(f"{STAFF_ID_PREFIX}%"),
        )
        .scalar_subquery()
    )
    return func.coalesce(last_member_message, Conversation.created_at)


async def list_cases(
    connection: AsyncConnection, *, status: str | None, done_since: datetime
) -> list[CaseListItem]:
    received = _received_at().label("received_at")
    fee_description = Proposal.evidence["fee"]["description"].astext.label("fee_description")
    query = (
        select(
            Case.conversation_id,
            Case.status,
            Case.category,
            Conversation.subject,
            MemberProfile.first_name,
            MemberProfile.last_name,
            Proposal.tier,
            fee_description,
            received,
        )
        .join(Conversation, Conversation.id == Case.conversation_id)
        .join(MemberProfile, MemberProfile.member_id == Conversation.member_id)
        .outerjoin(Proposal, Proposal.id == Case.current_proposal_id)
        .where(
            or_(
                Conversation.status != "closed",
                and_(Case.status.in_(DECIDED), Case.updated_at >= done_since),
            )
        )
        .order_by(received, Case.conversation_id)
    )
    if status is not None:
        query = query.where(Case.status == status)
    return [_list_item(row) for row in (await connection.execute(query)).all()]


def _list_item(row: Record) -> CaseListItem:
    return CaseListItem(
        id=row.conversation_id,
        member_name=f"{row.first_name} {row.last_name}",
        topic=labels.topic(row.category, row.fee_description, row.subject),
        status=row.status,
        status_label=labels.status_label(row.status),
        received_at=row.received_at,
        tier=row.tier,
    )


async def case_detail(
    connection: AsyncConnection, case_id: int, viewer: StaffMember, thresholds: Thresholds
) -> CaseDetail:
    head = await _case_head(connection, case_id)
    proposal = await _proposal(connection, head.current_proposal_id)
    evidence: dict[str, Any] = (proposal.evidence if proposal else None) or {}
    fee = evidence.get("fee")
    return CaseDetail(
        id=case_id,
        status=head.status,
        status_label=labels.status_label(head.status),
        topic=labels.topic(head.category, fee["description"] if fee else None, head.subject),
        received_at=head.received_at,
        member=await _member(connection, head),
        messages=await _messages(connection, case_id, head.first_name),
        proposal=_proposal_view(proposal, head, viewer, thresholds) if proposal else None,
        evidence=_evidence_view(evidence, thresholds) if proposal else None,
        run=await _latest_run(connection, case_id),
        decision=await _latest_decision(connection, case_id),
    )


async def _case_head(connection: AsyncConnection, case_id: int) -> Record:
    query = (
        select(
            Case.status,
            Case.category,
            Case.manual_reason_code,
            Case.current_proposal_id,
            Conversation.subject,
            Conversation.member_id,
            MemberProfile.first_name,
            MemberProfile.last_name,
            _received_at().label("received_at"),
        )
        .join(Conversation, Conversation.id == Case.conversation_id)
        .join(MemberProfile, MemberProfile.member_id == Conversation.member_id)
        .where(Case.conversation_id == case_id)
    )
    head = (await connection.execute(query)).first()
    if head is None:
        raise CaseNotFound(f"case {case_id}")
    return head


async def _proposal(connection: AsyncConnection, proposal_id: int | None) -> Record | None:
    if proposal_id is None:
        return None
    query = select(Proposal.__table__).where(Proposal.id == proposal_id)
    return (await connection.execute(query)).first()


async def _member(connection: AsyncConnection, head: Record) -> MemberView:
    credit_union = await connection.scalar(
        select(CreditUnion.name)
        .join(Account, Account.credit_union_id == CreditUnion.id)
        .where(Account.member_id == head.member_id)
        .order_by(Account.is_primary.desc())
        .limit(1)
    )
    flags = await connection.execute(
        select(MemberFlag.flag, MemberFlag.resolved_at).where(
            MemberFlag.member_id == head.member_id
        )
    )
    good = in_good_standing(StandingFlag(f.flag, f.resolved_at is not None) for f in flags)
    return MemberView(
        name=f"{head.first_name} {head.last_name}",
        standing="good" if good else "not_good",
        credit_union=credit_union or "",
    )


async def _messages(
    connection: AsyncConnection, case_id: int, first_name: str
) -> list[MessageView]:
    staff = await connection.execute(select(Staff.id, Staff.first_name))
    staff_names = {row.id: row.first_name for row in staff}
    rows = await connection.execute(
        select(Message.author_id, Message.body, Message.created_at)
        .where(Message.conversation_id == case_id)
        .order_by(Message.created_at, Message.id)
    )
    return [
        MessageView(
            sender="staff" if row.author_id.startswith(STAFF_ID_PREFIX) else "member",
            author_name=staff_names.get(row.author_id, first_name),
            body=row.body,
            sent_at=row.created_at,
        )
        for row in rows
    ]


def _proposal_view(
    proposal: Record, head: Record, viewer: StaffMember, thresholds: Thresholds
) -> ProposalView:
    evidence: dict[str, Any] = proposal.evidence or {}
    fee = evidence.get("fee")
    fee_name = labels.fee_label(fee["description"]) if fee else "fee"
    manual = head.manual_reason_code
    quote = proposal.policy_quote
    return ProposalView(
        recommendation=proposal.recommendation,
        reason_code=proposal.reason_code,
        tier=proposal.tier,
        headline=labels.headline(head.status, proposal.recommendation, proposal.amount, fee_name),
        authority_note=labels.authority_note(
            head.status, proposal.tier, viewer.role, proposal.amount, head.first_name
        ),
        amount=_money_text(proposal.amount),
        checks=[CheckView(**check) for check in (proposal.checks or {}).get("items", [])],
        policy_quote=PolicyQuoteView(
            document=quote["document_title"],
            text=quote["text"],
            slug=quote["document_slug"],
            passage_id=quote["passage_id"],
        )
        if quote
        else None,
        draft_reply=proposal.draft_reply,
        draft_source=proposal.draft_source,
        language=proposal.language,
        manual_reason=manual_reason_text(ReasonCode(manual), head.first_name, thresholds)
        if manual
        else None,
        fee_choices=_fee_choices(evidence) if manual == ReasonCode.AMBIGUOUS_FEE else [],
    )


def _fee_choices(evidence: dict[str, Any]) -> list[FeeChoiceView]:
    # ui.md §2.6: "Overdraft fee · Mon, Sep 8 · $35.00", never the id.
    return [
        FeeChoiceView(
            id=fee["id"],
            label=f"{labels.fee_label(fee['description'])} · {day(date.fromisoformat(fee['date']))}"
            f" · {money(abs(Decimal(fee['amount'])))}",
        )
        for fee in evidence.get("fee_candidates", [])
    ]


def _evidence_view(evidence: dict[str, Any], thresholds: Thresholds) -> EvidenceView:
    fee = evidence.get("fee")
    fee_id = fee["id"] if fee else None
    return EvidenceView(
        fee=_fee_view(fee) if fee else None,
        day_postings=[
            _posting_view(order, posting, fee_id)
            for order, posting in enumerate(evidence.get("day_postings", []), 1)
        ],
        refund_history=[
            RefundView(
                date=refund["date"],
                label=labels.display_description(refund["description"]),
                amount=refund["amount"],
            )
            for refund in evidence.get("refund_history", [])
        ],
        refunds_used=evidence.get("refunds_used"),
        refunds_limit=evidence.get("refunds_limit", thresholds.refund_limit_per_window),
    )


def _fee_view(fee: dict[str, Any]) -> FeeView:
    number = fee.get("account_number")
    account = (
        f"{fee['sub_account_name']} {mask_account(number)}" if number else fee["sub_account_name"]
    )
    return FeeView(
        label=labels.fee_label(fee["description"]),
        amount=fee["amount"],
        date=fee["date"],
        sub_account=fee["sub_account_name"],
        account=account,
        account_number_full=number,
    )


def _posting_view(order: int, posting: dict[str, Any], fee_id: int | None) -> PostingView:
    return PostingView(
        order=order,
        description=labels.display_description(posting["description"]),
        raw_description=posting["description"],
        amount=posting["amount"],
        balance_after=posting["balance_after"],
        is_fee=posting["id"] == fee_id,
    )


async def _latest_run(connection: AsyncConnection, case_id: int) -> RunView | None:
    run = (
        await connection.execute(
            select(AgentRun.id, AgentRun.status, AgentRun.total_latency_ms, AgentRun.total_cost_usd)
            .where(AgentRun.case_id == case_id, AgentRun.is_eval.is_(False))
            .order_by(AgentRun.started_at.desc())
            .limit(1)
        )
    ).first()
    if run is None:
        return None
    steps = await connection.execute(
        select(AgentStep.label, AgentStep.status, AgentStep.latency_ms)
        .where(AgentStep.run_id == run.id)
        .order_by(AgentStep.ordinal)
    )
    return RunView(
        status=run.status,
        duration_ms=run.total_latency_ms,
        cost_usd=str(run.total_cost_usd),
        steps=[StepView(label=s.label, status=s.status, duration_ms=s.latency_ms) for s in steps],
    )


async def _latest_decision(connection: AsyncConnection, case_id: int) -> DecisionView | None:
    row = (
        await connection.execute(
            select(Decision.action, Decision.outcome, Decision.created_at, Staff.first_name)
            .join(Staff, Staff.id == Decision.actor_id)
            .where(Decision.case_id == case_id)
            .order_by(Decision.created_at.desc(), Decision.id.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        return None
    return DecisionView(
        action=row.action, outcome=row.outcome, by=row.first_name, at=row.created_at
    )


def _money_text(amount: Decimal | None) -> str | None:
    return str(amount) if amount is not None else None


def done_since(now: datetime, window_hours: int) -> datetime:
    return now - timedelta(hours=window_hours)
