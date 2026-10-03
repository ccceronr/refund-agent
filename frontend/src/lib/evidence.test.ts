import { describe, expect, it } from 'vitest'
import type { Check, Evidence, Posting } from '../api/types'
import { hasEvidence, postingOrderCaption } from './evidence'

function posting(order: number, amount: string, isFee = false): Posting {
  return {
    order,
    description: '',
    raw_description: '',
    amount,
    balance_after: '0.00',
    is_fee: isFee,
  }
}
const qualifies: Check = { rule: 'BR-02', ok: true, text: '', warning: false }

describe('postingOrderCaption', () => {
  it('explains a deposit that was processed after the fee (ui.md §2.4)', () => {
    const day = [
      posting(1, '-60.00'),
      posting(2, '-35.00', true),
      posting(3, '1400.00'),
    ]

    expect(postingOrderCaption(day, [qualifies])).toBe(
      'The paycheck was processed after the fee. If it had come first, it would have covered the payment.',
    )
  })

  it('says nothing when the posting-order check failed', () => {
    const day = [
      posting(1, '-60.00'),
      posting(2, '-35.00', true),
      posting(3, '20.00'),
    ]

    expect(postingOrderCaption(day, [{ ...qualifies, ok: false }])).toBeNull()
  })

  it('says nothing when no deposit came after the fee', () => {
    const day = [posting(1, '1400.00'), posting(2, '-35.00', true)]

    expect(postingOrderCaption(day, [qualifies])).toBeNull()
  })
})

describe('hasEvidence', () => {
  const nothing: Evidence = {
    fee: null,
    day_postings: [],
    refund_history: [],
    refunds_used: null,
    refunds_limit: 3,
  }

  it('hides the panel when the run found nothing (e.g. injection suspected)', () => {
    expect(hasEvidence(nothing, null)).toBe(false)
  })

  it('shows past refunds even without an identified fee', () => {
    const refunds = [
      { date: '2026-03-03', label: 'Overdraft fee refund', amount: '35.00' },
    ]
    expect(hasEvidence({ ...nothing, refund_history: refunds }, null)).toBe(
      true,
    )
  })
})
