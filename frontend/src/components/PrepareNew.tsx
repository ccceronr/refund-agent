// "Prepare new messages (N)" (ui.md §2.1, R-03): the server prepares them one by one,
// and the AUTO tier refunds where it applies, without anyone opening the case.
import { LoaderCircle } from 'lucide-react'
import type { PrepareState } from '../hooks/usePrepareNew'

interface PrepareNewProps {
  count: number
  state: PrepareState
  onStart: () => void
}

export function PrepareNew({ count, state, onStart }: PrepareNewProps) {
  const running = state.phase === 'running'
  if (count === 0 && state.phase === 'idle') return null
  return (
    <div className="border-b border-grey-200 px-6 py-3" aria-live="polite">
      {count > 0 && (
        <button
          type="button"
          onClick={onStart}
          disabled={running}
          className="flex w-full items-center justify-center gap-2 rounded-md border border-grey-300 bg-white px-3 py-2 text-sm font-medium hover:border-navy disabled:cursor-wait disabled:text-grey-500"
        >
          {running && (
            <LoaderCircle aria-hidden className="size-4 animate-spin" />
          )}
          {running
            ? 'Preparing new messages…'
            : `Prepare new messages (${count})`}
        </button>
      )}
      {running && state.current && (
        <p className="mt-2 text-xs text-grey-500 tabular-nums">
          Preparing {state.current.index} of {state.current.total} ·{' '}
          {state.current.member_name}
        </p>
      )}
      {!running && state.summary && (
        <p
          role={state.phase === 'failed' ? 'alert' : 'status'}
          className="mt-2 text-xs text-grey-600"
        >
          {state.summary}
        </p>
      )}
    </div>
  )
}
