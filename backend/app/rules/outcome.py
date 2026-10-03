"""BR-07 (recommendation) and BR-08 (approval tier). The only place an outcome is decided.

The LLMs never change what these functions return (CLAUDE.md "The LLM never decides money").
"""

from app.rules import texts
from app.rules.checks import (
    PAST_FRAUD,
    already_refunded,
    covered_by_policy,
    in_good_standing,
    qualifies_by_posting_order,
    refund_amount,
    refunds_in_window,
    within_claim_window,
)
from app.rules.fees import fee_type
from app.rules.model import (
    AutoSignals,
    Evaluation,
    FeeType,
    ReasonCode,
    Recommendation,
    RuleInput,
    Thresholds,
    Tier,
    TierDecision,
)


def evaluate(case: RuleInput, thresholds: Thresholds) -> Evaluation:
    """Runs every check (all are returned for the UI), then the first BR-07 row that matches."""
    fee = case.fee
    kind = fee_type(fee.description)
    posting = qualifies_by_posting_order(fee, case.day_postings)
    used = refunds_in_window(case.refunds, case.as_of, window_days=thresholds.refund_window_days)
    left_after = thresholds.refund_limit_per_window - used - 1
    within = within_claim_window(fee, case.as_of, claim_window_days=thresholds.claim_window_days)
    refunded = already_refunded(
        fee, refunds=case.refunds, has_refund_action=case.fee_has_refund_action
    )
    good = in_good_standing(case.flags)
    covered = covered_by_policy(fee)
    limit_reached = used >= thresholds.refund_limit_per_window

    name = case.first_name
    checks = (
        texts.posting_order_check(name, fee.date, posting),
        texts.claim_window_check(name, fee.date, within, thresholds),
        texts.standing_check(name, good, past_fraud=any(f.flag == PAST_FRAUD for f in case.flags)),
        texts.refund_limit_check(name, used, left_after, thresholds),
        texts.already_refunded_check(refunded),
        texts.coverage_check(kind, covered),
    )
    # BR-07, top to bottom; the first true condition decides.
    outcome = (
        (refunded, Recommendation.NO_REFUND, ReasonCode.ALREADY_REFUNDED),
        (not covered, Recommendation.MANUAL, ReasonCode.FEE_TYPE_NOT_COVERED),
        (not within, Recommendation.NO_REFUND, ReasonCode.OUT_OF_WINDOW),
        (not good, Recommendation.NO_REFUND, ReasonCode.NOT_GOOD_STANDING),
        (not posting.qualifies, Recommendation.NO_REFUND, ReasonCode.NO_QUALIFYING_REASON),
        (limit_reached, Recommendation.NO_REFUND, ReasonCode.LIMIT_REACHED),
    )
    recommendation, reason = next(
        ((rec, code) for matched, rec, code in outcome if matched),
        (Recommendation.REFUND, ReasonCode.ELIGIBLE),
    )
    return Evaluation(
        recommendation=recommendation,
        reason_code=reason,
        fee_type=kind,
        amount=refund_amount(fee),
        refunds_in_window=used,
        refunds_left_after=left_after,
        checks=checks,
    )


def decide_tier(
    evaluation: Evaluation, signals: AutoSignals, thresholds: Thresholds
) -> TierDecision:
    """BR-08."""
    if evaluation.recommendation is Recommendation.MANUAL:
        return TierDecision(Tier.MANUAL, ())
    if evaluation.recommendation is Recommendation.NO_REFUND:
        return TierDecision(Tier.STAFF, ())
    if evaluation.amount > thresholds.staff_approval_limit:
        return TierDecision(Tier.SUPERVISOR, ())
    blockers = auto_blockers(evaluation, signals, thresholds)
    return TierDecision(Tier.STAFF if blockers else Tier.AUTO, blockers)


def auto_blockers(
    evaluation: Evaluation, signals: AutoSignals, thresholds: Thresholds
) -> tuple[str, ...]:
    """The BR-08 AUTO conditions that fail. Empty means the flow may refund on its own."""
    minimum = thresholds.auto_min_confidence
    fee_choice = signals.fee_choice
    failed = {
        "auto_disabled": not thresholds.auto_refund_enabled,
        "fee_type": evaluation.fee_type is not FeeType.COURTESY_PAY,
        "amount": evaluation.amount > thresholds.auto_refund_max_amount,
        # Never use the member's last available refund automatically.
        "last_refund": evaluation.refunds_left_after < 1,
        "fallback_used": any(a.source != "jev" for a in signals.typed_answers),
        "low_confidence": any(
            a.source == "jev" and a.confidence < minimum for a in signals.typed_answers
        ),
        "fee_choice": fee_choice is not None
        and (fee_choice.source != "jev" or fee_choice.confidence < minimum),
        "injection": signals.injection_probability > thresholds.auto_max_injection,
        "draft": signals.draft_source != "writer" or not signals.guard_passed,
    }
    return tuple(name for name, did_fail in failed.items() if did_fail)
