// The steps streaming in while a case is prepared (ui.md §2.8, R-16).
import { Check, LoaderCircle, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import type { RunState } from '../hooks/useCaseRun'
import { formatDuration } from '../lib/format'

interface RunProgressProps {
  run: RunState
  onRetry: () => void
}

export function RunProgress({ run, onRetry }: RunProgressProps) {
  return (
    <section
      aria-live="polite"
      aria-busy={run.phase === 'running'}
      className="rounded-xl border border-grey-200 bg-white p-6 shadow-sm"
    >
      <p className="text-xs font-semibold tracking-wide text-grey-500 uppercase">
        {run.phase === 'failed' ? 'Not prepared' : 'Preparing this case'}
      </p>
      <ol className="mt-3 space-y-1.5">
        <AnimatePresence initial={false}>
          {run.steps.map((step) => (
            <motion.li
              key={step.name}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
              className="flex items-center gap-2.5"
            >
              <StepIcon status={step.status} />
              <span
                className={step.status === 'running' ? '' : 'text-grey-600'}
              >
                {step.label}
              </span>
              {step.duration_ms !== null && (
                <span className="ml-auto text-sm text-grey-400 tabular-nums">
                  {formatDuration(step.duration_ms)}
                </span>
              )}
            </motion.li>
          ))}
        </AnimatePresence>
      </ol>
      {run.phase === 'failed' && (
        <div className="mt-4 border-t border-grey-100 pt-4">
          <p role="alert">{run.message}</p>
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 rounded-md border border-grey-300 px-3 py-1.5 font-medium hover:bg-grey-50"
          >
            Try again
          </button>
        </div>
      )}
    </section>
  )
}

function StepIcon({ status }: { status: RunState['steps'][number]['status'] }) {
  if (status === 'running') {
    return (
      <LoaderCircle
        aria-label="In progress"
        className="size-4 animate-spin text-grey-500"
      />
    )
  }
  if (status === 'failed')
    return <X aria-label="Failed" className="size-4 text-error" />
  return <Check aria-label="Done" className="size-4 text-success" />
}
