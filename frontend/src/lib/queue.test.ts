import { describe, expect, it } from 'vitest'
import type { CaseListItem } from '../api/types'
import { groupQueue, sectionFor } from './queue'

function item(id: number, status: CaseListItem['status']): CaseListItem {
  return {
    id,
    member_name: 'Ana Ruiz',
    topic: 'Overdraft fee refund',
    status,
    status_label: '',
    received_at: '2026-09-15T08:12:44',
    tier: null,
  }
}

describe('sectionFor', () => {
  it('puts every status in one of the six sections (ui.md §2.1)', () => {
    expect(sectionFor('ready')).toBe('ready')
    expect(sectionFor('new')).toBe('new')
    expect(sectionFor('running')).toBe('new')
    expect(sectionFor('manual_review')).toBe('review')
    expect(sectionFor('needs_supervisor')).toBe('supervisor')
    expect(sectionFor('not_refund')).toBe('not_refund')
    expect(sectionFor('resolved')).toBe('done')
    expect(sectionFor('auto_resolved')).toBe('done')
  })
})

describe('groupQueue', () => {
  const items = [
    item(1, 'new'),
    item(2, 'ready'),
    item(3, 'needs_supervisor'),
    item(4, 'manual_review'),
  ]

  it('puts new cases right after "Ready for you" and hides empty sections', () => {
    const sections = groupQueue(items, 'staff')

    expect(sections.map((s) => s.title)).toEqual([
      'Ready for you',
      'New',
      'Needs your review',
      'Needs a supervisor',
    ])
    expect(sections.map((s) => s.items.length)).toEqual([1, 1, 1, 1])
  })

  it('shows "Needs a supervisor" first to a supervisor', () => {
    expect(groupQueue(items, 'supervisor')[0]?.title).toBe('Needs a supervisor')
  })

  it('keeps the API order (oldest waiting first) inside a section', () => {
    const sections = groupQueue([item(7, 'ready'), item(4, 'ready')], 'staff')
    expect(sections[0]?.items.map((i) => i.id)).toEqual([7, 4])
  })
})
