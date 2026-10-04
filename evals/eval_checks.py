"""The checks of one eval case (seed-and-evals §3.2). Pure: no I/O.

A check is True (pass), False (fail) or None (does not apply to this case).
"""

import re
from decimal import Decimal
from typing import Any

from app.agents.proposal import ProposalPlan
from app.rules.model import Recommendation

EXPECTED_CHECKS = ("recommendation", "reason_code", "tier", "fee_date", "language", "case_status")
ALWAYS_CHECKS = ("guard_passed", "no_internal_terms", "amount_matches_ledger")
ALL_CHECKS = EXPECTED_CHECKS + ALWAYS_CHECKS

# ui.md §3: no internal terms, codes, model names or probabilities in what members read.
INTERNAL_TERMS = re.compile(
    r"\b(BR-\d+|ELIGIBLE|LIMIT_REACHED|NO_QUALIFYING_REASON|OUT_OF_WINDOW|NOT_GOOD_STANDING|"
    r"ALREADY_REFUNDED|FEE_TYPE_NOT_COVERED|INJECTION_SUSPECTED|INTENT_UNCLEAR|NO_FEE_FOUND|"
    r"AMBIGUOUS_FEE|tier|Jev|LLM|AI|agent|confidence|probability|Claude|Sonnet|Haiku|prompt)\b",
    re.IGNORECASE,
)
MONEY = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)")
Checks = dict[str, bool | None]


def check_case(expected: dict[str, Any], plan: ProposalPlan) -> Checks:
    actual = actual_values(plan)
    checks: Checks = dict.fromkeys(ALL_CHECKS)
    for name in EXPECTED_CHECKS:
        if name in expected:
            allowed = expected[name] if isinstance(expected[name], list) else [expected[name]]
            checks[name] = actual[name] in allowed
    checks["guard_passed"] = guard_passed(plan)
    checks["no_internal_terms"] = no_internal_terms(plan.draft_reply)
    checks["amount_matches_ledger"] = amount_matches_ledger(plan)
    return checks


def passed(checks: Checks) -> bool:
    return all(result is not False for result in checks.values())


def actual_values(plan: ProposalPlan) -> dict[str, Any]:
    fee = plan.evidence.get("fee")
    return {
        "recommendation": plan.recommendation.value,
        "reason_code": plan.reason_code,
        "tier": plan.tier.value,
        "fee_date": fee["date"] if fee else None,
        "language": plan.language,
        "case_status": plan.case_status,
        # What the always-on checks looked at, for the failure lines of the report.
        "guard_passed": f"draft from the {plan.draft_source}; guard failures "
        f"{plan.decisions.get('guard_failures') or 'none'}",
        "no_internal_terms": plan.draft_reply,
        "amount_matches_ledger": f"amount {plan.amount}; ledger fee {fee['amount'] if fee else None}",
    }


def guard_passed(plan: ProposalPlan) -> bool | None:
    """The writer's draft passed the output guard. N/A when no reply was written by the
    writer (manual review and not-a-refund use templates or nothing)."""
    if plan.recommendation is Recommendation.MANUAL:
        return None
    return plan.draft_source == "writer"


def no_internal_terms(draft: str | None) -> bool | None:
    if draft is None:
        return None
    return INTERNAL_TERMS.search(draft) is None


def amount_matches_ledger(plan: ProposalPlan) -> bool | None:
    """BR-10: the amount is the fee's own, and the reply mentions no other amount."""
    fee = plan.evidence.get("fee")
    if plan.amount is None or fee is None:
        return None
    ledger = abs(Decimal(fee["amount"]))
    mentioned = {Decimal(m.replace(",", "")) for m in MONEY.findall(plan.draft_reply or "")}
    return plan.amount == ledger and mentioned <= {ledger}
