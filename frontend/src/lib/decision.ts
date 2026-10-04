// What a decision may be and what it sends (design §4.3, ui.md §2.6, BR-09). The server
// checks BR-09 again on every decision: this only shapes what Luis is offered.
import type { Proposal, Role } from '../api/types'
import { formatMoney } from './format'

export type Outcome = 'refund' | 'no_refund'

export interface OutcomeOption {
  outcome: Outcome
  label: string
  enabled: boolean
  hint: string | null
}

export interface DecisionChoices {
  outcomes: OutcomeOption[] // empty: no choice to make
  proposed: Outcome
  needsFeePick: boolean
}

export type DecisionBody =
  | { action: 'approve' }
  | { action: 'reject'; reason: string }
  | {
      action: 'edit'
      outcome: Outcome
      reply_text: string
      fee_transaction_id?: number
    }

export interface DecisionDraft {
  outcome: Outcome
  reply: string
  feeId: number | null
}

// Refunding against these NO_REFUND reasons is a policy exception: supervisors only (BR-09).
const POLICY_EXCEPTIONS = new Set([
  'LIMIT_REACHED',
  'OUT_OF_WINDOW',
  'NOT_GOOD_STANDING',
  'NO_QUALIFYING_REASON',
])
const DONT_REFUND: OutcomeOption = {
  outcome: 'no_refund',
  label: "Don't refund",
  enabled: true,
  hint: null,
}

export function decisionChoices(
  proposal: Proposal,
  role: Role,
): DecisionChoices {
  const refundLabel = proposal.amount
    ? `Refund ${formatMoney(proposal.amount)}`
    : 'Refund'
  if (proposal.recommendation === 'REFUND') {
    return { outcomes: [], proposed: 'refund', needsFeePick: false }
  }
  if (proposal.recommendation === 'NO_REFUND') {
    if (!POLICY_EXCEPTIONS.has(proposal.reason_code)) {
      return { outcomes: [], proposed: 'no_refund', needsFeePick: false }
    }
    const supervisor = role === 'supervisor'
    const hint = supervisor
      ? null
      : 'Only a supervisor can make this exception.'
    const refund = {
      outcome: 'refund',
      label: refundLabel,
      enabled: supervisor,
      hint,
    } as const
    return {
      outcomes: [refund, DONT_REFUND],
      proposed: 'no_refund',
      needsFeePick: false,
    }
  }
  return manualChoices(proposal, refundLabel)
}

function manualChoices(
  proposal: Proposal,
  refundLabel: string,
): DecisionChoices {
  if (proposal.reason_code === 'AMBIGUOUS_FEE') {
    const refund = {
      outcome: 'refund',
      label: 'Refund the fee you pick',
      enabled: true,
      hint: null,
    } as const
    return {
      outcomes: [refund, DONT_REFUND],
      proposed: 'no_refund',
      needsFeePick: true,
    }
  }
  if (proposal.amount === null) {
    // No fee identified: a reply only (BR-09 "Manual cases").
    return { outcomes: [], proposed: 'no_refund', needsFeePick: false }
  }
  const refund = {
    outcome: 'refund',
    label: refundLabel,
    enabled: true,
    hint: null,
  } as const
  return {
    outcomes: [refund, DONT_REFUND],
    proposed: 'no_refund',
    needsFeePick: false,
  }
}

export function isChanged(
  proposal: Proposal,
  draft: DecisionDraft,
  proposed: Outcome,
): boolean {
  return (
    draft.outcome !== proposed || draft.reply !== (proposal.draft_reply ?? '')
  )
}

export function decisionBody(
  proposal: Proposal,
  draft: DecisionDraft,
): DecisionBody {
  const { proposed, needsFeePick } = decisionChoices(proposal, 'staff')
  const manual = proposal.recommendation === 'MANUAL'
  if (!manual && !isChanged(proposal, draft, proposed))
    return { action: 'approve' }
  const body: DecisionBody = {
    action: 'edit',
    outcome: draft.outcome,
    reply_text: draft.reply,
  }
  if (needsFeePick && draft.outcome === 'refund' && draft.feeId !== null) {
    return { ...body, fee_transaction_id: draft.feeId }
  }
  return body
}
