import { describe, expect, it } from 'vitest'
import {
  formatCost,
  formatDay,
  formatDuration,
  formatMoney,
  formatReceived,
  formatTime,
  relativeTime,
} from './format'

// ui.md §3: dates like "Mon, Sep 14"; times like "8:12 AM"; money "$35.00", negatives "−$60.00".
describe('formatMoney', () => {
  it('shows dollars with cents and thousands separators', () => {
    expect(formatMoney('1400.00')).toBe('$1,400.00')
  })

  it('uses a real minus sign for negative amounts', () => {
    expect(formatMoney('-60.00')).toBe('−$60.00')
  })

  it('pads missing cents', () => {
    expect(formatMoney('35')).toBe('$35.00')
  })
})

describe('dates and times', () => {
  it('formats a ledger day', () => {
    expect(formatDay('2026-09-14')).toBe('Mon, Sep 14')
  })

  it('formats a time of day', () => {
    expect(formatTime('2026-09-15T08:12:44')).toBe('8:12 AM')
  })

  it('formats when a message was received', () => {
    expect(formatReceived('2026-09-15T08:12:44')).toBe('Tue, Sep 15, 8:12 AM')
  })

  it('says how long ago, in short words', () => {
    const now = new Date(2026, 8, 15, 10, 12)
    expect(relativeTime('2026-09-15T10:11:30', now)).toBe('just now')
    expect(relativeTime('2026-09-15T09:40:00', now)).toBe('32 min ago')
    expect(relativeTime('2026-09-15T08:12:44', now)).toBe('2 h ago')
    expect(relativeTime('2026-09-13T08:12:44', now)).toBe('2 days ago')
    expect(relativeTime('2026-09-14T08:12:44', now)).toBe('1 day ago')
  })
})

describe('run figures', () => {
  it('shows durations in seconds with one decimal', () => {
    expect(formatDuration(4210)).toBe('4.2 s')
  })

  it('shows tiny costs to the tenth of a cent', () => {
    expect(formatCost('0.003740578')).toBe('$0.004')
    expect(formatCost('0.000025')).toBe('<$0.001')
  })
})
