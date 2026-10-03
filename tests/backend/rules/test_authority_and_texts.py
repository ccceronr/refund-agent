"""BR-09 approval authority, check texts and BR-13 manual reasons (business-rules.md)."""

import re
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.rules.authority import refund_authority
from app.rules.model import (
    LedgerEntry,
    ReasonCode,
    Role,
    RuleInput,
    StandingFlag,
    Thresholds,
    Verdict,
)
from app.rules.outcome import evaluate
from app.rules.texts import manual_reason_text

D = Decimal
THIRD_REFUND = LedgerEntry(1, 1302, date(2026, 6, 1), "Deposit Fee Refund Courtesy Pay Fee", D("35.00"), D("100.00"), "20260601-0000")  # fmt: skip
PRONOUNS = re.compile(r"\b(he|she|him|her|his|hers)\b", re.IGNORECASE)


def with_fee(case: RuleInput, **changes: object) -> RuleInput:
    fee = replace(case.fee, **changes)
    return replace(
        case, fee=fee, day_postings=tuple(fee if p.id == fee.id else p for p in case.day_postings)
    )


SITUATIONS = {
    "refund-within-limit": lambda c: c,
    "refund-above-limit": lambda c: with_fee(c, amount=D("-60.00")),
    "limit-reached": lambda c: replace(c, refunds=(*c.refunds, THIRD_REFUND)),
    "out-of-window": lambda c: replace(c, as_of=date(2026, 11, 20)),
    "not-good-standing": lambda c: replace(
        c, flags=(StandingFlag("DEBT_IN_COLLECTIONS", resolved=False),)
    ),
    "no-qualifying-reason": lambda c: replace(c, day_postings=c.day_postings[:2]),
    "not-covered-within-limit": lambda c: with_fee(
        c, description="Fee Withdrawal ; Excess Withdrawal Fee"
    ),
    "not-covered-above-limit": lambda c: with_fee(
        c, description="Fee Withdrawal ; Excess Withdrawal Fee", amount=D("-60.00")
    ),
    "already-refunded": lambda c: replace(c, fee_has_refund_action=True),
}

ALLOWED, SUPERVISOR, NEVER = Verdict.ALLOWED, Verdict.NEEDS_SUPERVISOR, Verdict.NEVER


@pytest.mark.parametrize(
    ("situation", "staff", "supervisor"),
    [
        ("refund-within-limit", ALLOWED, ALLOWED),
        ("refund-above-limit", SUPERVISOR, ALLOWED),
        ("limit-reached", SUPERVISOR, ALLOWED),
        ("out-of-window", SUPERVISOR, ALLOWED),
        ("not-good-standing", SUPERVISOR, ALLOWED),
        ("no-qualifying-reason", SUPERVISOR, ALLOWED),
        ("not-covered-within-limit", ALLOWED, ALLOWED),
        ("not-covered-above-limit", SUPERVISOR, ALLOWED),
        ("already-refunded", NEVER, NEVER),
    ],
)
def test_br09_matrix(
    ana: RuleInput, thresholds: Thresholds, situation: str, staff: Verdict, supervisor: Verdict
) -> None:
    evaluation = evaluate(SITUATIONS[situation](ana), thresholds)

    assert refund_authority(Role.STAFF, evaluation, "Ana", thresholds).verdict is staff
    assert refund_authority(Role.SUPERVISOR, evaluation, "Ana", thresholds).verdict is supervisor


def test_br09_the_automatic_flow_has_staff_authority_only(
    ana: RuleInput, thresholds: Thresholds
) -> None:
    evaluation = evaluate(SITUATIONS["limit-reached"](ana), thresholds)

    assert refund_authority(Role.SYSTEM, evaluation, "Ana", thresholds).verdict is SUPERVISOR


@pytest.mark.parametrize("role", [Role.STAFF, Role.SUPERVISOR])
def test_br09_a_manual_case_without_an_identified_fee_cannot_be_refunded(
    role: Role, thresholds: Thresholds
) -> None:
    decision = refund_authority(role, None, "Ana", thresholds)

    assert decision.verdict is Verdict.NO_FEE
    assert decision.message == "No fee was identified for this case, so it can't be refunded here."


def test_br09_refusal_message_from_the_spec(ana: RuleInput, thresholds: Thresholds) -> None:
    evaluation = evaluate(SITUATIONS["limit-reached"](ana), thresholds)

    message = refund_authority(Role.STAFF, evaluation, "Ana", thresholds).message

    assert message == (
        "This refund needs a supervisor's approval because Ana has already used every refund "
        "available this year."
    )


@pytest.mark.parametrize(
    "situation",
    [s for s in SITUATIONS if s not in {"refund-within-limit", "not-covered-within-limit"}],
)
def test_br09_every_refusal_explains_itself_in_plain_words(
    ana: RuleInput, thresholds: Thresholds, situation: str
) -> None:
    evaluation = evaluate(SITUATIONS[situation](ana), thresholds)

    message = refund_authority(Role.STAFF, evaluation, "Ana", thresholds).message

    assert message
    assert not re.search(r"BR-|[A-Z]{2,}_[A-Z]", message)


def test_ana_check_texts_match_the_spec_examples(ana: RuleInput, thresholds: Thresholds) -> None:
    checks = {c.rule: c for c in evaluate(ana, thresholds).checks}

    assert (
        checks["BR-02"].text
        == "Ana's paycheck of $1,400.00 arrived the same day and would have covered the payment."
    )
    assert checks["BR-03"].warning
    assert checks["BR-03"].text == "This is Ana's last refund available this year."


@pytest.mark.parametrize("situation", list(SITUATIONS))
def test_check_texts_name_the_member_and_use_no_gendered_pronouns(
    ana: RuleInput, thresholds: Thresholds, situation: str
) -> None:
    evaluation = evaluate(SITUATIONS[situation](ana), thresholds)

    for check in evaluation.checks:
        assert check.text
        assert not PRONOUNS.search(check.text), check.text


BR13 = {
    ReasonCode.INJECTION_SUSPECTED: "This message includes instructions aimed at our system. Please read it yourself before acting.",
    ReasonCode.INTENT_UNCLEAR: "I couldn't tell what Ana is asking for.",
    ReasonCode.NO_FEE_FOUND: "I couldn't find a fee on Ana's accounts in the last 60 days.",
    ReasonCode.AMBIGUOUS_FEE: "Ana has more than one recent fee and I can't tell which one Ana means.",
    ReasonCode.FEE_TYPE_NOT_COVERED: "This kind of fee isn't covered by the refund policy, so it's your call.",
    ReasonCode.AI_UNAVAILABLE: "The assistant wasn't available, so this case wasn't prepared. Try again, or handle it yourself.",
    ReasonCode.TIMEOUT: "Preparing this case took too long. Try again, or handle it yourself.",
    ReasonCode.DATA_UNAVAILABLE: "I couldn't read Ana's account information. Try again in a moment.",
    ReasonCode.REJECTED_BY_STAFF: "You rejected the suggestion. Handle this one yourself.",
}  # fmt: skip


@pytest.mark.parametrize(("code", "text"), list(BR13.items()))
def test_br13_manual_reason_texts(code: ReasonCode, text: str, thresholds: Thresholds) -> None:
    assert manual_reason_text(code, "Ana", thresholds) == text
