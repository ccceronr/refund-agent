import { describe, expect, it } from 'vitest'
import type { Proposal } from '../api/types'
import { decisionBody, decisionChoices } from './decision'

function proposal(overrides: Partial<Proposal> = {}): Proposal {
  return {
    recommendation: 'REFUND',
    reason_code: 'ELIGIBLE',
    tier: 'STAFF',
    headline: '',
    authority_note: null,
    amount: '35.00',
    checks: [],
    policy_quote: null,
    draft_reply: 'Hi Ana',
    draft_source: 'writer',
    language: 'en',
    manual_reason: null,
    fee_choices: [],
    ...overrides,
  }
}

// ui.md §2.6, BR-09 "Manual cases": what Luis (or Marta) may choose.
describe('decisionChoices', () => {
  it('offers no outcome choice on a refund proposal', () => {
    expect(decisionChoices(proposal(), 'staff').outcomes).toEqual([])
  })

  it('lets only a supervisor choose a refund that is a policy exception', () => {
    const limitReached = proposal({
      recommendation: 'NO_REFUND',
      reason_code: 'LIMIT_REACHED',
    })

    expect(decisionChoices(limitReached, 'staff').outcomes).toEqual([
      {
        outcome: 'refund',
        label: 'Refund $35.00',
        enabled: false,
        hint: 'Only a supervisor can make this exception.',
      },
      {
        outcome: 'no_refund',
        label: "Don't refund",
        enabled: true,
        hint: null,
      },
    ])
    expect(
      decisionChoices(limitReached, 'supervisor').outcomes[0]?.enabled,
    ).toBe(true)
  })

  it('never offers a refund for a fee that was already refunded', () => {
    const refunded = proposal({
      recommendation: 'NO_REFUND',
      reason_code: 'ALREADY_REFUNDED',
    })
    expect(decisionChoices(refunded, 'supervisor').outcomes).toEqual([])
  })

  it('asks Luis to pick the fee when it was ambiguous', () => {
    const ambiguous = proposal({
      recommendation: 'MANUAL',
      reason_code: 'AMBIGUOUS_FEE',
      amount: null,
    })
    const choices = decisionChoices(ambiguous, 'staff')

    expect(choices.needsFeePick).toBe(true)
    expect(choices.outcomes.map((o) => o.label)).toEqual([
      'Refund the fee you pick',
      "Don't refund",
    ])
    expect(choices.proposed).toBe('no_refund')
  })

  it('offers only a reply on a manual case with no fee', () => {
    const injection = proposal({
      recommendation: 'MANUAL',
      reason_code: 'INJECTION_SUSPECTED',
      amount: null,
    })
    expect(decisionChoices(injection, 'supervisor').outcomes).toEqual([])
  })
})

describe('decisionBody', () => {
  it('approves the proposal as it is when nothing changed', () => {
    expect(
      decisionBody(proposal(), {
        outcome: 'refund',
        reply: 'Hi Ana',
        feeId: null,
      }),
    ).toEqual({ action: 'approve' })
  })

  it('sends an edit with the outcome and the reply once something changed', () => {
    expect(
      decisionBody(proposal(), {
        outcome: 'refund',
        reply: 'Hi Ana!',
        feeId: null,
      }),
    ).toEqual({
      action: 'edit',
      outcome: 'refund',
      reply_text: 'Hi Ana!',
    })
  })

  it('names the picked fee only when refunding an ambiguous one', () => {
    const ambiguous = proposal({
      recommendation: 'MANUAL',
      reason_code: 'AMBIGUOUS_FEE',
      amount: null,
    })
    expect(
      decisionBody(ambiguous, { outcome: 'refund', reply: 'Hi', feeId: 7 }),
    ).toEqual({
      action: 'edit',
      outcome: 'refund',
      reply_text: 'Hi',
      fee_transaction_id: 7,
    })
    expect(
      decisionBody(ambiguous, { outcome: 'no_refund', reply: 'Hi', feeId: 7 }),
    ).toEqual({
      action: 'edit',
      outcome: 'no_refund',
      reply_text: 'Hi',
    })
  })
})
