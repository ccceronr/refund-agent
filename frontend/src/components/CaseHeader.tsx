// Who wrote, about what, and where the case stands (ui.md §2.2).
import type { CaseDetail } from '../api/types'
import { formatReceived, initials } from '../lib/format'
import { sectionFor } from '../lib/queue'
import { SECTION_STYLES } from './sectionStyles'

export function CaseHeader({ detail }: { detail: CaseDetail }) {
  const { icon: Icon, tint, ink } = SECTION_STYLES[sectionFor(detail.status)]
  return (
    <header className="flex flex-wrap items-center gap-x-4 gap-y-3">
      <span
        aria-hidden
        className="flex size-12 shrink-0 items-center justify-center rounded-full bg-terracotta/14 text-[17px] font-semibold"
      >
        {initials(detail.member.name)}
      </span>
      <div className="min-w-[13rem] flex-1">
        <h1 className="text-[1.75rem] leading-tight font-normal tracking-tight">
          {detail.member.name}
        </h1>
        <p className="text-grey-600">
          {detail.topic} · Received {formatReceived(detail.received_at)} ·{' '}
          {detail.member.credit_union}
        </p>
      </div>
      <span className={`chip h-8 px-3 text-sm ${tint}`}>
        <Icon aria-hidden className={`size-4 ${ink}`} />
        {detail.status_label}
      </span>
    </header>
  )
}
