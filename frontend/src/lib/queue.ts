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
