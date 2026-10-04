import { describe, expect, it } from 'vitest'
import { verdictTone } from './verdict'

// ui.md §2.3: the card shows the kind of outcome at a glance (icon + headline, never color alone).
describe('verdictTone', () => {
  it('follows the recommendation', () => {
    expect(verdictTone('ready', 'REFUND')).toBe('refund')
    expect(verdictTone('ready', 'NO_REFUND')).toBe('no_refund')
    expect(verdictTone('manual_review', 'MANUAL')).toBe('review')
  })

  it('shows an automatic refund as a refund', () => {
    expect(verdictTone('auto_resolved', 'REFUND')).toBe('refund')
  })

  it('keeps a message that is not a refund request neutral', () => {
    expect(verdictTone('not_refund', 'NO_REFUND')).toBe('other')
  })
})
