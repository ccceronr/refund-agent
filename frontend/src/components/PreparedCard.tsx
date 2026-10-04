// How the case was prepared (R-16, R-17): the steps of the latest run, how long it took
// and what it cost, folded away until Luis wants them. "Run again" prepares it once more.
import { Check, ChevronDown, RotateCw, X } from 'lucide-react'
import { Collapsible } from 'radix-ui'
import type { Run } from '../api/types'
import { formatCost, formatDuration } from '../lib/format'

interface PreparedCardProps {
  run: Run
  canRunAgain: boolean
  busy: boolean
  onRunAgain: () => void
}

export function PreparedCard({
  run,
  canRunAgain,
  busy,
  onRunAgain,
}: PreparedCardProps) {
  return (
    <Collapsible.Root className="card px-6 py-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Collapsible.Trigger className="group flex cursor-pointer items-center gap-2 font-semibold">
          <ChevronDown
            aria-hidden
            className="size-4 -rotate-90 transition-transform duration-200 group-data-[state=open]:rotate-0"
          />
          How this case was prepared
        </Collapsible.Trigger>
        <span className="text-sm text-grey-600 tabular-nums">
          Prepared in {formatDuration(run.duration_ms)} ·{' '}
          {formatCost(run.cost_usd)}
        </span>
        {canRunAgain && (
          <button
            type="button"
            onClick={onRunAgain}
            disabled={busy}
            className="button-quiet ml-auto h-8 text-sm"
          >
            <RotateCw aria-hidden className="size-3.5" />
            Run again
          </button>
        )}
      </div>
      <Collapsible.Content>
        <ol className="mt-3 space-y-2 border-t border-grey-100 pt-3">
          {run.steps.map((step) => (
            <li key={step.label} className="flex items-center gap-2.5 text-sm">
              {step.status === 'failed' ? (
                <X aria-label="Failed" className="size-4 shrink-0 text-error" />
              ) : (
                <Check
                  aria-label="Done"
                  className="size-4 shrink-0 text-success"
                />
              )}
              <span>{step.label}</span>
              {step.duration_ms !== null && (
                <span className="ml-auto text-grey-600 tabular-nums">
                  {formatDuration(step.duration_ms)}
                </span>
              )}
            </li>
          ))}
        </ol>
      </Collapsible.Content>
    </Collapsible.Root>
  )
}
