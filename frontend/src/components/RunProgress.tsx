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
      className="card p-5"
    >
      <p className="label">
        {run.phase === 'failed' ? 'Not prepared' : 'Preparing this case'}
      </p>
      <ol className="mt-3 space-y-2">
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
                <span className="ml-auto text-sm text-grey-600 tabular-nums">
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
            className="button-secondary mt-3"
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
        className="size-4 shrink-0 animate-spin text-grey-600"
      />
    )
  }
  if (status === 'failed')
    return <X aria-label="Failed" className="size-4 shrink-0 text-error" />
  return <Check aria-label="Done" className="size-4 shrink-0 text-success" />
}
