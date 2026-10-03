// The day timeline's caption (ui.md §2.4). Built from the BR-02 check the rules engine
// produced, never inferred on its own: it only explains a check that passed.
import type { Check, Evidence, Posting, Proposal } from '../api/types'

const POSTING_ORDER_RULE = 'BR-02'

export function postingOrderCaption(
  postings: Posting[],
  checks: Check[],
): string | null {
  const postingOrder = checks.find((check) => check.rule === POSTING_ORDER_RULE)
  const fee = postings.find((p) => p.is_fee)
  if (!postingOrder?.ok || !fee) return null
  const depositAfterFee = postings.some(
    (p) => p.order > fee.order && !p.amount.startsWith('-'),
  )
  if (!depositAfterFee) return null
  return 'The paycheck was processed after the fee. If it had come first, it would have covered the payment.'
}

// A manual case may have found nothing to show (e.g. stopped before reading any account).
export function hasEvidence(
  evidence: Evidence,
  proposal: Proposal | null,
): boolean {
  const feesFound = proposal?.fee_choices.length ?? 0
  return (
    evidence.fee !== null || evidence.refund_history.length > 0 || feesFound > 0
  )
}
