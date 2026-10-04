// The queue (ui.md §2.1): grouped sections, oldest waiting first, selected item marked.
import { LoaderCircle } from 'lucide-react'
import { useCases } from '../api/hooks'
import { usePrepareNew } from '../hooks/usePrepareNew'
import type { CaseListItem, Role } from '../api/types'
import { relativeTime } from '../lib/format'
import { groupQueue, queueNote, type QueueSection } from '../lib/queue'
import { PrepareNew } from './PrepareNew'
import { SECTION_STYLES } from './sectionStyles'

interface QueueProps {
  role: Role
  selectedId: number | null
  onSelect: (id: number) => void
}

export function Queue({ role, selectedId, onSelect }: QueueProps) {
  const cases = useCases()
  const [prepare, startPrepare] = usePrepareNew()
  const newCount =
    cases.data?.filter((item) => item.status === 'new').length ?? 0

  return (
    <nav aria-label="Conversations" className="pb-6">
      <PrepareNew count={newCount} state={prepare} onStart={startPrepare} />
      {cases.isPending && <QueueSkeleton />}
      {cases.error && (
        <p role="alert" className="px-5 py-4 text-error">
          {cases.error.message}
        </p>
      )}
      {cases.data?.length === 0 && (
        <p className="px-5 py-4 text-grey-600">You're all caught up.</p>
      )}
      {cases.data &&
        groupQueue(cases.data, role).map((section) => (
          <QueueGroup
            key={section.key}
            section={section}
            selectedId={selectedId}
            onSelect={onSelect}
          />
        ))}
    </nav>
  )
}

interface QueueGroupProps {
  section: QueueSection
  selectedId: number | null
  onSelect: (id: number) => void
}

function QueueGroup({ section, selectedId, onSelect }: QueueGroupProps) {
  const Icon = SECTION_STYLES[section.key].icon
  // "Ready for you" is what Luis works through first: its count is the one in navy.
  const count =
    section.key === 'ready' ? 'bg-navy text-white' : 'bg-navy/8 text-grey-700'
  return (
    <section aria-labelledby={`queue-${section.key}`} className="pt-5">
      <h2
        id={`queue-${section.key}`}
        className="flex items-center gap-2 px-5 pb-1.5 text-[13px] font-medium text-grey-600"
      >
        <Icon aria-hidden className="size-4" />
        {section.title}
        <span
          className={`ml-auto rounded-full px-2 text-xs font-semibold tabular-nums ${count}`}
        >
          {section.items.length}
        </span>
      </h2>
      <ul className="space-y-0.5 px-2">
        {section.items.map((item) => (
          <QueueItem
            key={item.id}
            item={item}
            selected={item.id === selectedId}
            onSelect={onSelect}
          />
        ))}
      </ul>
    </section>
  )
}

interface QueueItemProps {
  item: CaseListItem
  selected: boolean
  onSelect: (id: number) => void
}

function QueueItem({ item, selected, onSelect }: QueueItemProps) {
  const note = queueNote(item)
  return (
    <li>
      <button
        type="button"
        aria-current={selected ? 'true' : undefined}
        onClick={() => onSelect(item.id)}
        className={`relative block w-full cursor-pointer rounded-xl px-3 py-2.5 text-left transition-colors duration-150 ${
          selected ? 'bg-white' : 'hover:bg-white/60 active:bg-white'
        }`}
      >
        {selected && (
          <span
            aria-hidden
            className="absolute inset-y-2.5 left-0 w-[3px] rounded-full bg-terracotta"
          />
        )}
        <span className="flex items-baseline gap-3">
          <span
            className={`truncate ${selected ? 'font-semibold' : 'font-medium'}`}
          >
            {item.member_name}
          </span>
          <span className="ml-auto shrink-0 text-xs text-grey-600 tabular-nums">
            {relativeTime(item.received_at, new Date())}
          </span>
        </span>
        <span className="block truncate text-sm text-grey-600">
          {item.topic}
        </span>
        {note && (
          <span className="mt-0.5 flex items-center gap-1.5 text-xs text-grey-600">
            {item.status === 'running' && (
              <LoaderCircle aria-hidden className="size-3 animate-spin" />
            )}
            {note}
          </span>
        )}
      </button>
    </li>
  )
}

const SKELETON_ROWS = 6

function QueueSkeleton() {
  return (
    <div aria-busy="true" className="space-y-4 px-5 pt-6">
      <span className="sr-only">Loading conversations…</span>
      {Array.from({ length: SKELETON_ROWS }, (_, row) => (
        <div key={row} className="space-y-1.5">
          <div className="skeleton h-4 w-2/5" />
          <div className="skeleton h-3.5 w-3/5" />
        </div>
      ))}
    </div>
  )
}
