// The queue (ui.md §2.1): grouped sections, oldest waiting first, selected item marked.
import { useCases } from '../api/hooks'
import type { CaseListItem, Role } from '../api/types'
import { relativeTime } from '../lib/format'
import { groupQueue } from '../lib/queue'

interface QueueProps {
  role: Role
  selectedId: number | null
  onSelect: (id: number) => void
}

export function Queue({ role, selectedId, onSelect }: QueueProps) {
  const cases = useCases()

  return (
    <nav
      aria-label="Conversations"
      className="border-b border-grey-200 lg:h-[calc(100vh-57px)] lg:overflow-y-auto lg:border-r lg:border-b-0"
    >
      {cases.isPending && (
        <p className="p-6 text-grey-500">Loading conversations…</p>
      )}
      {cases.error && (
        <p role="alert" className="p-6 text-error">
          {cases.error.message}
        </p>
      )}
      {cases.data?.length === 0 && (
        <p className="p-6 text-grey-500">You're all caught up.</p>
      )}
      {cases.data &&
        groupQueue(cases.data, role).map((section) => (
          <section
            key={section.key}
            aria-labelledby={`queue-${section.key}`}
            className="py-3"
          >
            <h2
              id={`queue-${section.key}`}
              className="flex items-center justify-between px-6 py-1 text-xs font-semibold tracking-wide text-grey-500 uppercase"
            >
              {section.title}
              <span className="tabular-nums">{section.items.length}</span>
            </h2>
            <ul>
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
        ))}
    </nav>
  )
}

interface QueueItemProps {
  item: CaseListItem
  selected: boolean
  onSelect: (id: number) => void
}

function QueueItem({ item, selected, onSelect }: QueueItemProps) {
  return (
    <li>
      <button
        type="button"
        aria-current={selected ? 'true' : undefined}
        onClick={() => onSelect(item.id)}
        className={`block w-full border-l-[3px] px-6 py-2.5 text-left transition-colors ${
          selected
            ? 'border-terracotta bg-white'
            : 'border-transparent hover:bg-white/60'
        }`}
      >
        <span className="block font-medium">{item.member_name}</span>
        <span className="block truncate text-sm text-grey-600">
          {item.topic}
        </span>
        <span className="block text-xs text-grey-500">
          {item.status_label} · {relativeTime(item.received_at, new Date())}
        </span>
      </button>
    </li>
  )
}
