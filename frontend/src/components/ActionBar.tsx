// Sticky actions (ui.md §2.7): the primary action, an inline reject form (no modal, so
// the CSP stays strict), plain-language errors and the run figures.
import { Check } from 'lucide-react'
import { motion } from 'motion/react'
import { type FormEvent, useEffect, useState } from 'react'
import type { CaseDetail } from '../api/types'
import type { DecisionResult } from '../hooks/useDecision'
import type { Actions } from '../lib/actions'
import { formatCost, formatDuration } from '../lib/format'

const REASON_MAX = 500

interface ActionBarProps {
  detail: CaseDetail
  actions: Actions
  pending: boolean
  error: Error | null
  result: DecisionResult | undefined
  running: boolean
  onPrimary: () => void
  onReject: (reason: string) => void
  onRunAgain: () => void
}

export function ActionBar(props: ActionBarProps) {
  const { detail, actions, pending, error, result, running, onPrimary } = props
  const [rejecting, setRejecting] = useState(false)
  const canPrimary = actions.primary?.enabled === true && !pending && !rejecting
  useApproveShortcut(canPrimary, onPrimary)
  const decided =
    detail.status === 'resolved' || detail.status === 'auto_resolved'

  return (
    <div className="sticky bottom-0 border-t border-grey-200 bg-white/95 backdrop-blur-sm">
      <div className="mx-auto max-w-3xl px-6 py-3 lg:px-10">
        {error && (
          <p role="alert" className="mb-2 text-sm text-error">
            {error.message}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          {result ? (
            <Success result={result} />
          ) : (
            <Buttons
              {...props}
              canPrimary={canPrimary}
              rejecting={rejecting}
              onStartReject={() => setRejecting(true)}
            />
          )}
          <p className="ml-auto flex items-center gap-3 text-sm text-grey-500 tabular-nums">
            {detail.run && (
              <span>
                Prepared in {formatDuration(detail.run.duration_ms)} ·{' '}
                {formatCost(detail.run.cost_usd)}
              </span>
            )}
            {!decided && detail.proposal && (
              <button
                type="button"
                onClick={props.onRunAgain}
                disabled={running || pending}
                className="text-navy underline-offset-2 hover:underline disabled:text-grey-400"
              >
                Run again
              </button>
            )}
          </p>
        </div>
        {rejecting && !result && (
          <RejectForm
            pending={pending}
            onCancel={() => setRejecting(false)}
            onConfirm={(reason) => props.onReject(reason)}
          />
        )}
      </div>
    </div>
  )
}

interface ButtonsProps extends ActionBarProps {
  canPrimary: boolean
  rejecting: boolean
  onStartReject: () => void
}

function Buttons({
  actions,
  pending,
  canPrimary,
  rejecting,
  onPrimary,
  onStartReject,
}: ButtonsProps) {
  return (
    <>
      {actions.primary && (
        <button
          type="button"
          disabled={!canPrimary}
          onClick={onPrimary}
          title={canPrimary ? 'Ctrl + Enter' : undefined}
          className="rounded-md bg-navy px-4 py-2 font-medium text-white hover:opacity-90 disabled:bg-grey-300 disabled:text-grey-600"
        >
          {pending ? 'Sending…' : actions.primary.label}
        </button>
      )}
      {actions.canReject && !rejecting && (
        <button
          type="button"
          disabled={pending}
          onClick={onStartReject}
          className="rounded-md border border-grey-300 px-4 py-2 font-medium hover:bg-grey-50"
        >
          Reject
        </button>
      )}
    </>
  )
}

function Success({ result }: { result: DecisionResult }) {
  const text = result.refunded
    ? 'Refunded and sent'
    : result.action === 'reject'
      ? 'Rejected. The case is back in your review list.'
      : 'Reply sent'
  return (
    <motion.p
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      role="status"
      className="flex items-center gap-2 font-medium text-success"
    >
      <Check aria-hidden className="size-5" />
      {text}
    </motion.p>
  )
}

interface RejectFormProps {
  pending: boolean
  onCancel: () => void
  onConfirm: (reason: string) => void
}

function RejectForm({ pending, onCancel, onConfirm }: RejectFormProps) {
  const [reason, setReason] = useState('')
  const valid = reason.trim().length > 0

  function submit(event: FormEvent) {
    event.preventDefault()
    if (valid) onConfirm(reason.trim())
  }

  return (
    <form
      onSubmit={submit}
      className="mt-3 space-y-2 border-t border-grey-100 pt-3"
    >
      <label htmlFor="reject-reason" className="block text-sm font-medium">
        What's wrong with this suggestion?
      </label>
      <textarea
        id="reject-reason"
        autoFocus
        required
        maxLength={REASON_MAX}
        rows={2}
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        className="w-full rounded-md border border-grey-300 p-2"
      />
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={!valid || pending}
          className="rounded-md bg-navy px-3 py-1.5 font-medium text-white disabled:bg-grey-300"
        >
          {pending ? 'Rejecting…' : 'Reject suggestion'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md px-3 py-1.5 hover:bg-grey-100"
        >
          Cancel
        </button>
      </div>
    </form>
  )
}

// ui.md §2.7: ⌘/Ctrl + Enter runs the primary action.
function useApproveShortcut(enabled: boolean, onPrimary: () => void): void {
  useEffect(() => {
    if (!enabled) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
        event.preventDefault()
        onPrimary()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [enabled, onPrimary])
}
