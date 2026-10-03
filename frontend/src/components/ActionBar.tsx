// Sticky actions (ui.md §2.7). P7a shows the right buttons; they are wired in P7b.
import type { CaseDetail, Role } from '../api/types'
import { availableActions } from '../lib/actions'
import { formatCost, formatDuration } from '../lib/format'

interface ActionBarProps {
  detail: CaseDetail
  role: Role
  edited: boolean
}

export function ActionBar({ detail, role, edited }: ActionBarProps) {
  const { primary, canReject } = availableActions(detail, role, edited)
  if (!primary && !detail.run) return null
  return (
    <div className="sticky bottom-0 border-t border-grey-200 bg-white/95 backdrop-blur-sm">
      <div className="mx-auto flex max-w-3xl flex-wrap items-center gap-3 px-6 py-3 lg:px-10">
        {primary && (
          <button
            type="button"
            disabled={!primary.enabled}
            className="rounded-md bg-navy px-4 py-2 font-medium text-white hover:opacity-90 disabled:bg-grey-300 disabled:text-grey-600"
          >
            {primary.label}
          </button>
        )}
        {canReject && (
          <button
            type="button"
            className="rounded-md border border-grey-300 px-4 py-2 font-medium hover:bg-grey-50"
          >
            Reject
          </button>
        )}
        {detail.run && (
          <p className="ml-auto text-sm text-grey-500 tabular-nums">
            Prepared in {formatDuration(detail.run.duration_ms)} ·{' '}
            {formatCost(detail.run.cost_usd)}
          </p>
        )}
      </div>
    </div>
  )
}
