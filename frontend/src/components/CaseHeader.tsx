import type { CaseDetail } from '../api/types'
import { formatReceived } from '../lib/format'

export function CaseHeader({ detail }: { detail: CaseDetail }) {
  return (
    <header>
      <h1 className="font-serif text-2xl">
        {detail.member.name} <span className="text-grey-400">·</span>{' '}
        {detail.topic}
      </h1>
      <p className="text-sm text-grey-500">
        Received {formatReceived(detail.received_at)} ·{' '}
        {detail.member.credit_union}
      </p>
    </header>
  )
}
