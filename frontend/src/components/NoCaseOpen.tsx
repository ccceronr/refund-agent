// The case area before a case is opened (desktop, ui.md §2): how much is waiting in each
// section, and the next case to decide. On a narrow screen the list shows instead.
import type { CaseListItem, Staff } from '../api/types'
import { formatReceived, initials } from '../lib/format'
import { sectionCounts, type SectionKey } from '../lib/queue'
import { SECTION_STYLES } from './sectionStyles'

const OVERVIEW: { key: SectionKey; title: string }[] = [
  { key: 'ready', title: 'Ready for you' },
  { key: 'review', title: 'Needs your review' },
  { key: 'supervisor', title: 'Needs a supervisor' },
  { key: 'done', title: 'Done today' },
]

interface NoCaseOpenProps {
  staff: Staff
  cases: CaseListItem[]
  next: CaseListItem | null
  onOpen: (id: number) => void
}

export function NoCaseOpen({ staff, cases, next, onOpen }: NoCaseOpenProps) {
  const counts = sectionCounts(cases)
  return (
    <div className="mx-auto max-w-5xl px-6 py-10 lg:px-10">
      <h1 className="text-[2rem] leading-tight font-normal tracking-tight">
        Hi {staff.name}, here's what's waiting
      </h1>
      <ul className="mt-6 grid grid-cols-2 gap-4 @3xl:grid-cols-4">
        {OVERVIEW.map(({ key, title }) => (
          <OverviewCard
            key={key}
            section={key}
            title={title}
            count={counts[key]}
          />
        ))}
      </ul>
      {next ? (
        <NextUp next={next} onOpen={onOpen} />
      ) : (
        <p className="mt-8 text-grey-600">
          Nothing is ready to decide. Choose a conversation from the list to see
          it here.
        </p>
      )}
    </div>
  )
}

interface OverviewCardProps {
  section: SectionKey
  title: string
  count: number
}

function OverviewCard({ section, title, count }: OverviewCardProps) {
  const { icon: Icon, tint, ink } = SECTION_STYLES[section]
  return (
    <li className="card flex items-center gap-4 p-5">
      <span aria-hidden className={`icon-tile size-11 ${tint} ${ink}`}>
        <Icon className="size-5" />
      </span>
      <span>
        <span className="block text-sm text-grey-600">{title}</span>
        <span className="block text-3xl leading-tight font-medium tabular-nums">
          {count}
        </span>
      </span>
    </li>
  )
}

function NextUp({
  next,
  onOpen,
}: {
  next: CaseListItem
  onOpen: (id: number) => void
}) {
  return (
    <section
      aria-labelledby="next-up"
      className="card mt-6 flex flex-wrap items-center gap-x-5 gap-y-4 p-6"
    >
      <span
        aria-hidden
        className="flex size-12 items-center justify-center rounded-full bg-terracotta/14 font-semibold text-navy"
      >
        {initials(next.member_name)}
      </span>
      <div className="min-w-0 flex-1">
        <h2 id="next-up" className="label">
          Next up · waiting the longest
        </h2>
        <p className="text-lg font-medium">
          {next.member_name} · {next.topic}
        </p>
        <p className="text-sm text-grey-600">
          Received {formatReceived(next.received_at)}
        </p>
      </div>
      <button
        type="button"
        onClick={() => onOpen(next.id)}
        className="button-primary"
      >
        Open {next.member_name}'s case
      </button>
    </section>
  )
}
