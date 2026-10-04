// Queue sections (ui.md §2.1): which status goes where, and in which order.
import type { CaseListItem, CaseStatus, Role } from '../api/types'

export type SectionKey =
  'ready' | 'new' | 'review' | 'supervisor' | 'not_refund' | 'done'

export interface QueueSection {
  key: SectionKey
  title: string
  items: CaseListItem[]
}

const TITLES: Record<SectionKey, string> = {
  ready: 'Ready for you',
  new: 'New',
  review: 'Needs your review',
  supervisor: 'Needs a supervisor',
  not_refund: 'Not a refund',
  done: 'Done today',
}
const STAFF_ORDER: SectionKey[] = [
  'ready',
  'new',
  'review',
  'supervisor',
  'not_refund',
  'done',
]
const SUPERVISOR_ORDER: SectionKey[] = [
  'supervisor',
  'ready',
  'new',
  'review',
  'not_refund',
  'done',
]

const SECTION_BY_STATUS: Record<CaseStatus, SectionKey> = {
  ready: 'ready',
  new: 'new',
  running: 'new',
  manual_review: 'review',
  needs_supervisor: 'supervisor',
  not_refund: 'not_refund',
  resolved: 'done',
  auto_resolved: 'done',
}

export function sectionFor(status: CaseStatus): SectionKey {
  return SECTION_BY_STATUS[status]
}

export function groupQueue(items: CaseListItem[], role: Role): QueueSection[] {
  const order = role === 'supervisor' ? SUPERVISOR_ORDER : STAFF_ORDER
  return order
    .map((key) => ({
      key,
      title: TITLES[key],
      items: items.filter((item) => sectionFor(item.status) === key),
    }))
    .filter((section) => section.items.length > 0)
}

// The overview cards before a case is opened (ui.md §2): how many cases wait in each section.
export function sectionCounts(
  items: CaseListItem[],
): Record<SectionKey, number> {
  const counts: Record<SectionKey, number> = {
    ready: 0,
    new: 0,
    review: 0,
    supervisor: 0,
    not_refund: 0,
    done: 0,
  }
  for (const item of items) counts[sectionFor(item.status)] += 1
  return counts
}

// "Next case" after a decision (ui.md §2.7): the oldest case that is quick to decide.
// A supervisor sees the cases waiting for a supervisor first, as in the queue.
const NEXT_SECTIONS: Record<Role, SectionKey[]> = {
  staff: ['ready'],
  supervisor: ['supervisor', 'ready'],
}

export function nextCase(
  items: CaseListItem[],
  currentId: number | null,
  role: Role,
): CaseListItem | null {
  for (const key of NEXT_SECTIONS[role]) {
    const found = items.find(
      (item) => item.id !== currentId && sectionFor(item.status) === key,
    )
    if (found) return found
  }
  return null
}

// The section title already names most statuses; only the ones that share a section with
// another status need their own label (ui.md §2.1).
const NOTED_STATUSES = new Set<CaseStatus>(['running', 'auto_resolved'])

export function queueNote(item: CaseListItem): string | null {
  if (item.asked_by) return `Asked by ${item.asked_by}` // sent to a supervisor (§2.7)
  return NOTED_STATUSES.has(item.status) ? item.status_label : null
}
