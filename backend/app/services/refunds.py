"""RefundService.execute: the ONLY code path that moves money (BR-11).

Used by the automatic tier and by staff decisions alike. It runs inside the caller's
transaction (app_rw), so a failure anywhere rolls everything back. In this demo the
"core banking system" is the same Postgres; this service is the adapter a real core
integration would replace.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import Integer, cast, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.models import Account, RefundAction, SubAccount, Transaction
from app.rules.authority import refund_authority
from app.rules.fees import REFUND_PREFIX, fee_type_text
from app.rules.model import ReasonCode, Role, Thresholds, Verdict
from app.rules.outcome import evaluate
from app.services import audit
from app.services.errors import ApprovalNotAllowed, FeeAlreadyRefunded, NoFeeIdentified
from app.tools.evidence import read_rule_input
from app.tools.queries import get_fee, load_case


@dataclass(frozen=True)
class Actor:
    staff_id: str
    role: Role


@dataclass(frozen=True)
class RefundResult:
    refund_transaction_id: int
    amount: Decimal
    sub_account_id: int


class RefundService:
    def __init__(self, thresholds: Thresholds, today: Callable[[], date] = date.today) -> None:
        self._thresholds = thresholds
        self._today = today

    async def execute(
        self,
        connection: AsyncConnection,
        *,
        case_id: int,
        fee_transaction_id: int,
        actor: Actor,
        idempotency_key: str,
    ) -> RefundResult:
        case = await load_case(connection, case_id)
        fee = await get_fee(connection, fee_transaction_id)
        if fee is None or not await _belongs_to(
            connection, fee.transaction.sub_account_id, case.member_id
        ):
            raise NoFeeIdentified("the fee is not one of this member's fees")
        sub_account = await _lock_sub_account(connection, fee.transaction.sub_account_id)
        today = self._today()
        as_of = case.as_of.date()
        rule_input = await read_rule_input(
            connection,
            case,
            fee,
            self._thresholds,
            refunds_until=max(as_of, today),  # BR-05 must see refunds made after the message
        )
        evaluation = evaluate(rule_input, self._thresholds)
        if evaluation.reason_code is ReasonCode.ALREADY_REFUNDED:
            raise FeeAlreadyRefunded(f"fee {fee_transaction_id} was already refunded")
        authority = refund_authority(actor.role, evaluation, case.first_name, self._thresholds)
        if authority.verdict is not Verdict.ALLOWED:
            raise ApprovalNotAllowed(authority.message or "This refund isn't allowed.")

        amount = evaluation.amount  # BR-10: from the ledger, never from a request or a model
        balance_after = sub_account.balance + amount
        inserted = await connection.execute(
            insert(Transaction)
            .values(
                sub_account_id=sub_account.id,
                date=today,
                description=f"{REFUND_PREFIX} {fee_type_text(fee.transaction.description)}",
                amount=amount,
                balance_after=balance_after,
                posting_ref=await _next_posting_ref(connection, sub_account.id, today),
            )
            .returning(Transaction.id)
        )
        refund_id: int = inserted.scalar_one()
        await connection.execute(
            update(SubAccount)
            .where(SubAccount.id == sub_account.id)
            .values(balance=SubAccount.balance + amount, available=SubAccount.available + amount)
        )
        await _record_refund_action(
            connection, case_id, fee_transaction_id, refund_id, amount, actor
        )
        await audit.record(
            connection,
            event="refund_executed",
            actor_id=actor.staff_id,
            case_id=case_id,
            details={
                "fee_transaction_id": fee_transaction_id,
                "refund_transaction_id": refund_id,
                "amount": str(amount),
                "reason_code": evaluation.reason_code.value,
                "idempotency_key": idempotency_key,
            },
        )
        return RefundResult(
            refund_transaction_id=refund_id, amount=amount, sub_account_id=sub_account.id
        )


async def _belongs_to(connection: AsyncConnection, sub_account_id: int, member_id: int) -> bool:
    owner = await connection.scalar(
        select(Account.member_id)
        .join(SubAccount, SubAccount.account_id == Account.id)
        .where(SubAccount.id == sub_account_id)
    )
    return owner == member_id


@dataclass(frozen=True)
class _LockedSubAccount:
    id: int
    balance: Decimal


async def _lock_sub_account(connection: AsyncConnection, sub_account_id: int) -> _LockedSubAccount:
    # Serializes refunds on one sub-account: balance and posting order stay consistent.
    row = (
        await connection.execute(
            select(SubAccount.id, SubAccount.balance)
            .where(SubAccount.id == sub_account_id)
            .with_for_update()
        )
    ).one()
    return _LockedSubAccount(id=row.id, balance=row.balance)


async def _next_posting_ref(connection: AsyncConnection, sub_account_id: int, day: date) -> str:
    last = await connection.scalar(
        select(func.max(cast(func.split_part(Transaction.posting_ref, "-", 2), Integer))).where(
            Transaction.sub_account_id == sub_account_id, Transaction.date == day
        )
    )
    position = 0 if last is None else last + 1
    return f"{day:%Y%m%d}-{position:04d}"


async def _record_refund_action(
    connection: AsyncConnection,
    case_id: int,
    fee_transaction_id: int,
    refund_transaction_id: int,
    amount: Decimal,
    actor: Actor,
) -> None:
    try:
        async with connection.begin_nested():
            await connection.execute(
                insert(RefundAction).values(
                    case_id=case_id,
                    fee_transaction_id=fee_transaction_id,
                    refund_transaction_id=refund_transaction_id,
                    amount=amount,
                    actor_id=actor.staff_id,
                )
            )
    except IntegrityError as error:
        # R-15: the unique constraints are the last line of defence against a double refund.
        raise FeeAlreadyRefunded(
            f"fee {fee_transaction_id} or case {case_id} already refunded"
        ) from error
