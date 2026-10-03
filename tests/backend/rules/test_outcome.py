"""BR-07 outcome (first match wins, every check returned) and BR-08 tiers (business-rules.md)."""

from collections.abc import Callable
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.rules.model import (
    AutoSignals,
    LedgerEntry,
    ReasonCode,
    Recommendation,
    RuleInput,
    StandingFlag,
    Thresholds,
    Tier,
    TypedAnswer,
)
from app.rules.outcome import decide_tier, evaluate

D = Decimal
Mutation = Callable[[RuleInput], RuleInput]

THIRD_REFUND = LedgerEntry(1, 1302, date(2026, 6, 1), "Deposit Fee Refund Courtesy Pay Fee", D("35.00"), D("100.00"), "20260601-0000")  # fmt: skip
JULY_REFUND = LedgerEntry(2, 1302, date(2026, 7, 1), "Deposit Fee Refund Courtesy Pay Fee", D("35.00"), D("1.00"), "20260701-0000")  # fmt: skip


def already_refunded(case: RuleInput) -> RuleInput:
    return replace(case, fee_has_refund_action=True)


def not_covered(case: RuleInput) -> RuleInput:
    fee = replace(case.fee, description="Fee Withdrawal ; Excess Withdrawal Fee")
    return replace(
        case, fee=fee, day_postings=tuple(fee if p.id == fee.id else p for p in case.day_postings)
    )


def out_of_window(case: RuleInput) -> RuleInput:
    return replace(case, as_of=date(2026, 11, 20))  # 67 days after the fee


def not_in_good_standing(case: RuleInput) -> RuleInput:
    return replace(case, flags=(StandingFlag("PAST_FRAUD", resolved=True),))


def no_qualifying_reason(case: RuleInput) -> RuleInput:
    return replace(case, day_postings=case.day_postings[:2])  # drop the payroll


def limit_reached(case: RuleInput) -> RuleInput:
    return replace(case, refunds=(*case.refunds, THIRD_REFUND))


def apply(case: RuleInput, *mutations: Mutation) -> RuleInput:
    for mutation in mutations:
        case = mutation(case)
    return case


@pytest.mark.parametrize(
    ("mutations", "recommendation", "reason"),
    [
        ((already_refunded,), Recommendation.NO_REFUND, ReasonCode.ALREADY_REFUNDED),
        ((not_covered,), Recommendation.MANUAL, ReasonCode.FEE_TYPE_NOT_COVERED),
        ((out_of_window,), Recommendation.NO_REFUND, ReasonCode.OUT_OF_WINDOW),
        ((not_in_good_standing,), Recommendation.NO_REFUND, ReasonCode.NOT_GOOD_STANDING),
        ((no_qualifying_reason,), Recommendation.NO_REFUND, ReasonCode.NO_QUALIFYING_REASON),
        ((limit_reached,), Recommendation.NO_REFUND, ReasonCode.LIMIT_REACHED),
        ((), Recommendation.REFUND, ReasonCode.ELIGIBLE),
    ],
    ids=["row1", "row2", "row3", "row4", "row5", "row6", "row7"],
)
def test_br07_each_row_of_the_table(
    ana: RuleInput,
    thresholds: Thresholds,
    mutations: tuple[Mutation, ...],
    recommendation: Recommendation,
    reason: ReasonCode,
) -> None:
    result = evaluate(apply(ana, *mutations), thresholds)

    assert (result.recommendation, result.reason_code) == (recommendation, reason)


@pytest.mark.parametrize(
    ("mutations", "reason"),
    [
        (
            (
                already_refunded,
                not_covered,
                out_of_window,
                not_in_good_standing,
                no_qualifying_reason,
                limit_reached,
            ),
            ReasonCode.ALREADY_REFUNDED,
        ),
        (
            (not_covered, out_of_window, not_in_good_standing, no_qualifying_reason, limit_reached),
            ReasonCode.FEE_TYPE_NOT_COVERED,
        ),
        (
            (out_of_window, not_in_good_standing, no_qualifying_reason, limit_reached),
            ReasonCode.OUT_OF_WINDOW,
        ),
        ((not_in_good_standing, no_qualifying_reason, limit_reached), ReasonCode.NOT_GOOD_STANDING),
        ((no_qualifying_reason, limit_reached), ReasonCode.NO_QUALIFYING_REASON),
    ],
    ids=["1-over-all", "2-over-3..6", "3-over-4..6", "4-over-5..6", "5-over-6"],
)
def test_br07_the_first_matching_row_wins(
    ana: RuleInput, thresholds: Thresholds, mutations: tuple[Mutation, ...], reason: ReasonCode
) -> None:
    assert evaluate(apply(ana, *mutations), thresholds).reason_code is reason


def test_br07_every_check_is_returned_even_after_a_match(
    ana: RuleInput, thresholds: Thresholds
) -> None:
    result = evaluate(apply(ana, already_refunded, no_qualifying_reason), thresholds)

    assert [c.rule for c in result.checks] == ["BR-02", "BR-04", "BR-06", "BR-03", "BR-05", "BR-01"]
    assert {c.rule: c.ok for c in result.checks} == {
        "BR-02": False, "BR-04": True, "BR-06": True, "BR-03": True, "BR-05": False, "BR-01": True,
    }  # fmt: skip


def test_ana_is_refunded_35_with_no_refunds_left_after(
    ana: RuleInput, thresholds: Thresholds
) -> None:
    result = evaluate(ana, thresholds)

    assert result.amount == D("35.00")
    assert (result.refunds_in_window, result.refunds_left_after) == (2, 0)


# --- BR-08 --------------------------------------------------------------------------


def test_br08_manual_recommendation_is_the_manual_tier(ana, thresholds, clean_signals) -> None:
    assert (
        decide_tier(evaluate(not_covered(ana), thresholds), clean_signals, thresholds).tier
        is Tier.MANUAL
    )


def test_br08_no_refund_is_the_staff_tier(ana, thresholds, clean_signals) -> None:
    assert (
        decide_tier(evaluate(limit_reached(ana), thresholds), clean_signals, thresholds).tier
        is Tier.STAFF
    )


def test_br08_refund_above_the_staff_limit_needs_a_supervisor(
    ana, thresholds, clean_signals
) -> None:
    fee = replace(ana.fee, amount=D("-60.00"))
    case = replace(ana, fee=fee, day_postings=(ana.day_postings[0], fee, ana.day_postings[2]))

    assert (
        decide_tier(evaluate(case, thresholds), clean_signals, thresholds).tier is Tier.SUPERVISOR
    )


def test_br08_refund_meeting_every_auto_condition_is_automatic(
    ana_with_refunds_left, thresholds, clean_signals
) -> None:
    decision = decide_tier(evaluate(ana_with_refunds_left, thresholds), clean_signals, thresholds)

    assert (decision.tier, decision.auto_blockers) == (Tier.AUTO, ())


def test_br08_ana_with_her_last_refund_is_the_staff_tier(ana, thresholds, clean_signals) -> None:
    decision = decide_tier(evaluate(ana, thresholds), clean_signals, thresholds)

    assert decision.tier is Tier.STAFF
    assert decision.auto_blockers == ("last_refund",)


def _nsf(case: RuleInput) -> RuleInput:
    fee = replace(case.fee, description="Fee Withdrawal ; NSF fee")
    return replace(
        case, fee=fee, day_postings=tuple(fee if p.id == fee.id else p for p in case.day_postings)
    )


def _amount(value: str) -> Mutation:
    def change(case: RuleInput) -> RuleInput:
        fee = replace(case.fee, amount=D(value))
        return replace(
            case,
            fee=fee,
            day_postings=tuple(fee if p.id == fee.id else p for p in case.day_postings),
        )

    return change


SignalChange = Callable[[AutoSignals], AutoSignals]


@pytest.mark.parametrize(
    ("case_change", "signal_change", "threshold_change", "blocker"),
    [
        (None, None, {"auto_refund_enabled": False}, "auto_disabled"),
        (_nsf, None, None, "fee_type"),
        (_amount("-40.00"), None, None, "amount"),
        (lambda c: replace(c, refunds=(*c.refunds, JULY_REFUND)), None, None, "last_refund"),
        (
            None,
            lambda s: replace(s, typed_answers=(TypedAnswer("fallback", 0.9),)),
            None,
            "fallback_used",
        ),
        (
            None,
            lambda s: replace(s, typed_answers=(TypedAnswer("jev", 0.94),)),
            None,
            "low_confidence",
        ),
        (None, lambda s: replace(s, fee_choice=TypedAnswer("jev", 0.94)), None, "fee_choice"),
        (None, lambda s: replace(s, fee_choice=TypedAnswer("fallback", 0.99)), None, "fee_choice"),
        (None, lambda s: replace(s, injection_probability=0.11), None, "injection"),
        (None, lambda s: replace(s, draft_source="template"), None, "draft"),
        (None, lambda s: replace(s, guard_passed=False), None, "draft"),
    ],
    ids=[
        "disabled",
        "nsf",
        "amount-40",
        "last-refund",
        "fallback",
        "jev-0.94",
        "fee-choice-0.94",
        "fee-choice-fallback",
        "injection-0.11",
        "template",
        "guard-failed",
    ],
)
def test_br08_each_auto_condition_failing_alone_falls_back_to_staff(
    ana_with_refunds_left,
    thresholds,
    clean_signals,
    case_change,
    signal_change,
    threshold_change,
    blocker,
) -> None:
    case = case_change(ana_with_refunds_left) if case_change else ana_with_refunds_left
    signals = signal_change(clean_signals) if signal_change else clean_signals
    limits = replace(thresholds, **threshold_change) if threshold_change else thresholds

    decision = decide_tier(evaluate(case, limits), signals, limits)

    assert decision.tier is Tier.STAFF
    assert decision.auto_blockers == (blocker,)


@pytest.mark.parametrize(
    "signal_change",
    [
        lambda s: replace(s, typed_answers=(TypedAnswer("jev", 0.95),)),
        lambda s: replace(s, fee_choice=TypedAnswer("jev", 0.95)),
        lambda s: replace(s, injection_probability=0.1),
    ],
    ids=["confidence-exactly-0.95", "fee-choice-exactly-0.95", "injection-exactly-0.1"],
)
def test_br08_auto_limits_are_inclusive(
    ana_with_refunds_left, thresholds, clean_signals, signal_change
) -> None:
    decision = decide_tier(
        evaluate(ana_with_refunds_left, thresholds), signal_change(clean_signals), thresholds
    )

    assert decision.tier is Tier.AUTO


def test_br08_amount_exactly_35_can_be_automatic(
    ana_with_refunds_left, thresholds, clean_signals
) -> None:
    case = _amount("-35.00")(ana_with_refunds_left)

    assert decide_tier(evaluate(case, thresholds), clean_signals, thresholds).tier is Tier.AUTO
