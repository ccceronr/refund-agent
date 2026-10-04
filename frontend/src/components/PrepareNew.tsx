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
    <div className="px-5 pt-2" aria-live="polite">
      {count > 0 && (
        <button
          type="button"
          onClick={onStart}
          disabled={running}
          className="button w-full bg-terracotta font-semibold text-navy hover:bg-terracotta/90 active:bg-terracotta/80 disabled:cursor-wait disabled:bg-white disabled:text-grey-600"
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
        <div className="mt-3">
          {/* A native <progress>: accessible, and no inline styles under the strict CSP. */}
          <progress
            value={state.current.index}
            max={state.current.total}
            aria-label="Preparing new messages"
            className="block h-1 w-full appearance-none overflow-hidden rounded-full bg-white [&::-moz-progress-bar]:bg-terracotta [&::-webkit-progress-bar]:bg-white [&::-webkit-progress-value]:bg-terracotta [&::-webkit-progress-value]:transition-all"
          />
          <p className="mt-1.5 text-xs text-grey-600 tabular-nums">
            Preparing {state.current.index} of {state.current.total} ·{' '}
            {state.current.member_name}
          </p>
        </div>
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
