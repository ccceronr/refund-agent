"""The eval checks (seed-and-evals §3.2): pure functions over the saved plan."""

from dataclasses import replace
from decimal import Decimal

from eval_checks import check_case, passed

from app.agents.proposal import ProposalPlan
from app.rules.model import Recommendation, Tier

FEE = {"date": "2026-09-14", "amount": "-35.00", "description": "Fee Withdrawal ; Courtesy Pay fee"}
PLAN = ProposalPlan(
    recommendation=Recommendation.REFUND, reason_code="ELIGIBLE", tier=Tier.STAFF,
    auto_blockers=("last_refund",), case_status="ready", category="fee_refund",
    manual_reason_code=None, fee_transaction_id=88002, amount=Decimal("35.00"), checks=[],
    evidence={"fee": FEE}, policy_quote=None, language="en", tone="neutral",
    draft_reply="Hi Ana,\n\nWe've refunded the $35.00 overdraft fee.", draft_source="writer",
    decisions={},
)  # fmt: skip
EXPECTED = {
    "recommendation": "REFUND",
    "reason_code": "ELIGIBLE",
    "tier": ["STAFF"],
    "fee_date": "2026-09-14",
    "language": "en",
    "case_status": "ready",
}


def test_a_matching_plan_passes_every_check() -> None:
    checks = check_case(EXPECTED, PLAN)

    assert passed(checks)
    assert all(checks[name] for name in EXPECTED)


def test_a_tier_list_accepts_any_of_its_values() -> None:
    assert check_case({"tier": ["STAFF", "AUTO"]}, replace(PLAN, tier=Tier.AUTO))["tier"] is True


def test_only_the_expected_keys_are_checked() -> None:
    checks = check_case(
        {"case_status": ["manual_review", "not_refund"]}, replace(PLAN, case_status="not_refund")
    )

    assert checks["case_status"] is True
    assert checks["recommendation"] is None


def test_a_reply_with_internal_terms_fails() -> None:
    leaky = replace(PLAN, draft_reply="Your case is ELIGIBLE under BR-02 (tier STAFF).")

    assert check_case({}, leaky)["no_internal_terms"] is False


def test_a_reply_that_mentions_another_amount_fails_the_ledger_check() -> None:
    wrong = replace(PLAN, draft_reply="We've refunded $500.00 to your account.")

    assert check_case({}, wrong)["amount_matches_ledger"] is False


def test_a_template_reply_on_a_refund_means_the_guard_did_not_pass() -> None:
    assert check_case({}, replace(PLAN, draft_source="template"))["guard_passed"] is False


def test_manual_cases_skip_the_reply_checks_that_do_not_apply() -> None:
    manual = replace(
        PLAN,
        recommendation=Recommendation.MANUAL,
        amount=None,
        evidence={},
        draft_source="template",
    )

    checks = check_case({}, manual)

    assert checks["guard_passed"] is None
    assert checks["amount_matches_ledger"] is None
    assert passed(checks)
