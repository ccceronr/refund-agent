"""Read-only queries for the agent flow (R-07, R-10). Run them on an agent_ro connection.

They return ledger facts only. Every judgement (fee type, exact window edges, outcome)
belongs to the rules engine, so date ranges come in as arguments, inclusive on both ends.
"""

import re
from collections import defaultdict
from datetime import date
from typing import Any

from sqlalchemy import ColumnElement, Integer, Select, cast, func, select
from sqlalchemy.dialects.postgresql import REGCONFIG
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.models import (
    Account,
    Conversation,
    CreditUnion,
    MemberFlag,
    MemberProfile,
    Message,
    PolicyDocument,
    PolicyPassage,
    RefundAction,
    SubAccount,
    Transaction,
)
from app.tools.schemas import (
    CaseContext,
    FeeCandidate,
    LedgerTransaction,
    MemberAccount,
    MemberMessage,
    MemberStanding,
    PolicyHit,
    StandingFlag,
    SubAccountInfo,
)

# business-rules.md "Definitions".
FEE_PREFIX = "Fee Withdrawal"
REFUND_PREFIX = "Deposit Fee Refund"
POLICY_HITS = 5  # design §6.1: top 5 passages go to Jev


class CaseDataMissing(LookupError):
    """The conversation, its member or a member message is missing (DATA_UNAVAILABLE)."""


async def load_case(connection: AsyncConnection, conversation_id: int) -> CaseContext:
    head = (
        await connection.execute(
            select(
                Conversation.member_id,
                Conversation.subject,
                MemberProfile.first_name,
                MemberProfile.last_name,
            )
            .join(MemberProfile, MemberProfile.member_id == Conversation.member_id)
            .where(Conversation.id == conversation_id)
        )
    ).one_or_none()
    if head is None:
        raise CaseDataMissing(f"conversation {conversation_id} or its member profile")
    messages = await _member_messages(connection, conversation_id, head.member_id)
    if not messages:
        raise CaseDataMissing(f"conversation {conversation_id} has no member message")
    return CaseContext(
        conversation_id=conversation_id,
        member_id=head.member_id,
        first_name=head.first_name,
        last_name=head.last_name,
        credit_union_name=await _credit_union_name(connection, head.member_id),
        subject=head.subject,
        member_messages=messages,
        as_of=messages[-1].sent_at,
    )


async def get_member_accounts(connection: AsyncConnection, member_id: int) -> list[MemberAccount]:
    rows = await connection.execute(
        select(
            Account.id,
            Account.account_number,
            Account.is_primary,
            SubAccount.id.label("sub_id"),
            SubAccount.type,
            SubAccount.name,
            SubAccount.balance,
            SubAccount.available,
        )
        .join(SubAccount, SubAccount.account_id == Account.id)
        .where(Account.member_id == member_id)
        .order_by(Account.is_primary.desc(), Account.id, SubAccount.id)
    )
    accounts: dict[int, MemberAccount] = {}
    sub_accounts: defaultdict[int, list[SubAccountInfo]] = defaultdict(list)
    for row in rows:
        accounts.setdefault(
            row.id,
            MemberAccount(
                id=row.id,
                account_number=row.account_number,
                is_primary=row.is_primary,
                sub_accounts=[],
            ),
        )
        sub_accounts[row.id].append(
            SubAccountInfo(
                id=row.sub_id,
                type=row.type,
                name=row.name,
                balance=row.balance,
                available=row.available,
            )
        )
    return [
        account.model_copy(update={"sub_accounts": sub_accounts[account.id]})
        for account in accounts.values()
    ]


async def find_fee_candidates(
    connection: AsyncConnection, member_id: int, *, since: date, until: date
) -> list[FeeCandidate]:
    """Fee transactions in the member scope, including fees already refunded."""
    query = (
        _member_transactions(member_id, since, until)
        .add_columns(RefundAction.id.is_not(None).label("has_refund_action"))
        .outerjoin(RefundAction, RefundAction.fee_transaction_id == Transaction.id)
        .where(
            Transaction.amount < 0, Transaction.description.startswith(FEE_PREFIX, autoescape=True)
        )
    )
    rows = await connection.execute(query)
    return [
        FeeCandidate(transaction=_ledger(row), has_refund_action=row.has_refund_action)
        for row in rows
    ]


async def get_fee(connection: AsyncConnection, transaction_id: int) -> FeeCandidate | None:
    """One fee transaction with its refund_actions flag (BR-05), whoever the member is."""
    row = (
        await connection.execute(
            _transactions()
            .add_columns(RefundAction.id.is_not(None).label("has_refund_action"))
            .outerjoin(RefundAction, RefundAction.fee_transaction_id == Transaction.id)
            .where(Transaction.id == transaction_id, Transaction.amount < 0)
            .where(Transaction.description.startswith(FEE_PREFIX, autoescape=True))
        )
    ).one_or_none()
    if row is None:
        return None
    return FeeCandidate(transaction=_ledger(row), has_refund_action=row.has_refund_action)


async def get_day_postings(
    connection: AsyncConnection, sub_account_id: int, day: date
) -> list[LedgerTransaction]:
    rows = await connection.execute(
        _transactions().where(Transaction.sub_account_id == sub_account_id, Transaction.date == day)
    )
    return [_ledger(row) for row in rows]


async def get_refund_history(
    connection: AsyncConnection, member_id: int, *, since: date, until: date
) -> list[LedgerTransaction]:
    """Refund transactions of any fee type, across all the member's sub-accounts (BR-03)."""
    rows = await connection.execute(
        _member_transactions(member_id, since, until).where(
            Transaction.amount > 0,
            Transaction.description.startswith(REFUND_PREFIX, autoescape=True),
        )
    )
    return [_ledger(row) for row in rows]


async def get_member_standing(connection: AsyncConnection, member_id: int) -> MemberStanding:
    rows = await connection.execute(
        select(MemberFlag.flag, MemberFlag.created_at, MemberFlag.resolved_at)
        .where(MemberFlag.member_id == member_id)
        .order_by(MemberFlag.created_at)
    )
    flags = [
        StandingFlag(flag=r.flag, created_at=r.created_at, resolved_at=r.resolved_at) for r in rows
    ]
    return MemberStanding(flags=flags)


async def search_policy(
    connection: AsyncConnection, query: str, limit: int = POLICY_HITS
) -> list[PolicyHit]:
    """Full-text search over the seeded policies (R-10). The text is only ever a bound value."""
    search_text = _any_of_the_words(query)
    if not search_text:
        return []
    tsquery = func.websearch_to_tsquery(cast("english", REGCONFIG), search_text)
    rank = func.ts_rank(PolicyPassage.tsv, tsquery).label("rank")
    rows = await connection.execute(
        select(
            PolicyPassage.id, PolicyPassage.text, PolicyDocument.slug, PolicyDocument.title, rank
        )
        .join(PolicyDocument, PolicyDocument.id == PolicyPassage.document_id)
        .where(PolicyPassage.tsv.op("@@")(tsquery))
        .order_by(rank.desc(), PolicyPassage.id)
        .limit(limit)
    )
    return [
        PolicyHit(
            passage_id=r.id, document_slug=r.slug, document_title=r.title, text=r.text, rank=r.rank
        )
        for r in rows
    ]


def _any_of_the_words(query: str) -> str:
    # websearch_to_tsquery ANDs plain words, and no passage holds all the words of a
    # query like "refund limit per member 12 months"; OR them and let ts_rank order.
    return " or ".join(re.findall(r"\w+", query))


async def _member_messages(
    connection: AsyncConnection, conversation_id: int, member_id: int
) -> list[MemberMessage]:
    rows = await connection.execute(
        select(Message.body, Message.created_at)
        .where(Message.conversation_id == conversation_id, Message.author_id == str(member_id))
        .order_by(Message.created_at, Message.id)
    )
    return [MemberMessage(body=r.body, sent_at=r.created_at) for r in rows]


async def _credit_union_name(connection: AsyncConnection, member_id: int) -> str:
    name = await connection.scalar(
        select(CreditUnion.name)
        .join(Account, Account.credit_union_id == CreditUnion.id)
        .where(Account.member_id == member_id)
        .order_by(Account.is_primary.desc(), Account.id)
        .limit(1)
    )
    if name is None:
        raise CaseDataMissing(f"member {member_id} has no account")
    return name


def _posting_order() -> ColumnElement[int]:
    # business-rules.md: order within a day is the numeric suffix of posting_ref.
    return cast(func.split_part(Transaction.posting_ref, "-", 2), Integer)


def _transactions() -> Select[*tuple[Any, ...]]:  # row shape varies by caller
    return (
        select(
            Transaction.id,
            Transaction.sub_account_id,
            SubAccount.name.label("sub_account_name"),
            Transaction.date,
            Transaction.description,
            Transaction.amount,
            Transaction.balance_after,
            Transaction.posting_ref,
        )
        .join(SubAccount, SubAccount.id == Transaction.sub_account_id)
        .order_by(Transaction.date, _posting_order())
    )


def _member_transactions(
    member_id: int, since: date, until: date
) -> Select[*tuple[Any, ...]]:  # row shape varies by caller
    return (
        _transactions()
        .join(Account, Account.id == SubAccount.account_id)
        .where(Account.member_id == member_id, Transaction.date.between(since, until))
    )


def _ledger(row: object) -> LedgerTransaction:
    return LedgerTransaction.model_validate(row, from_attributes=True)
