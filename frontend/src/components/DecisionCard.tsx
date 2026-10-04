// The decision (ui.md §2.7), next to the recommendation: what money would move, the
// primary action, an inline reject form (no modal, so the CSP stays strict), plain-language
// errors, and the next case once it's done.
import { Check, LoaderCircle, Lock } from 'lucide-react'
import { motion } from 'motion/react'
import { type FormEvent, type ReactNode, useEffect, useState } from 'react'
import type { CaseDetail, Fee } from '../api/types'
import type { DecisionResult } from '../hooks/useDecision'
import type { Actions } from '../lib/actions'
import { formatDay, formatMoney } from '../lib/format'

const REASON_MAX = 500

interface DecisionCardProps {
  detail: CaseDetail
  actions: Actions
  pending: boolean
  error: Error | null
  result: DecisionResult | undefined
  onPrimary: () => void
  onReject: (reason: string) => void
  canAskSupervisor: boolean
  asking: boolean // sending the case to a supervisor
  onAskSupervisor: () => void
  onNext: (() => void) | null
  children: ReactNode // the outcome and fee choices, when Luis has to pick
}

export function DecisionCard(props: DecisionCardProps) {
  const { detail, actions, pending, error, result, onPrimary } = props
  const [rejecting, setRejecting] = useState(false)
  const canPrimary =
    actions.primary?.enabled === true && !pending && !props.asking && !rejecting
  useApproveShortcut(canPrimary, onPrimary)

  return (
    <section aria-label="Your decision" className="card space-y-4 p-5">
      {detail.evidence?.fee && !result && (
        <FeeDetails fee={detail.evidence.fee} />
      )}
      {!result && props.children}
      {error && (
        <p role="alert" className="text-sm text-error">
          {error.message}
        </p>
      )}
      {detail.asked_by && !result && (
        <p className="text-sm text-grey-600">
          {detail.asked_by} asked a supervisor to decide this.
        </p>
      )}
      {result ? (
        <Success result={result} onNext={props.onNext} />
      ) : (
        <Buttons
          {...props}
          canPrimary={canPrimary}
          rejecting={rejecting}
          onStartReject={() => setRejecting(true)}
        />
      )}
      {rejecting && !result && (
        <RejectForm
          pending={pending}
          onCancel={() => setRejecting(false)}
          onConfirm={(reason) => props.onReject(reason)}
        />
      )}
    </section>
  )
}

// The fee the decision is about, so Luis sees exactly which money would move (BR-10).
function FeeDetails({ fee }: { fee: Fee }) {
  return (
    <div className="rounded-xl bg-clay/70 px-4 py-3">
      <p className="flex items-baseline justify-between gap-3">
        <span className="font-medium">
          {fee.label} · {formatDay(fee.date)}
        </span>
        <span className="text-lg font-semibold tabular-nums">
          {formatMoney(fee.amount.replace('-', ''))}
        </span>
      </p>
      <p className="text-sm text-grey-600">{fee.account}</p>
    </div>
  )
}

interface ButtonsProps extends DecisionCardProps {
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
  canAskSupervisor,
  asking,
  onAskSupervisor,
}: ButtonsProps) {
  const busy = pending || asking
  const primary = actions.primary
  // The only approval that can't be clicked is the one waiting for a supervisor (BR-09).
  const locked = primary?.kind === 'approve' && !primary.enabled
  return (
    <div className="space-y-2">
      {primary && (
        <button
          type="button"
          disabled={!canPrimary}
          onClick={onPrimary}
          aria-keyshortcuts="Control+Enter Meta+Enter"
          className="button-primary h-11 w-full"
        >
          {pending && (
            <LoaderCircle aria-hidden className="size-4 animate-spin" />
          )}
          {locked && <Lock aria-hidden className="size-4" />}
          {pending ? 'Sending…' : primary.label}
        </button>
      )}
      {canAskSupervisor && !rejecting && (
        <button
          type="button"
          disabled={busy}
          onClick={onAskSupervisor}
          className="button-secondary w-full"
        >
          {asking && (
            <LoaderCircle aria-hidden className="size-4 animate-spin" />
          )}
          Ask a supervisor
        </button>
      )}
      {actions.canReject && !rejecting && (
        <button
          type="button"
          disabled={busy}
          onClick={onStartReject}
          className="button-secondary w-full"
        >
          Reject
        </button>
      )}
      {canPrimary && <ShortcutHint />}
    </div>
  )
}

const IS_MAC = /Mac|iPhone|iPad/.test(navigator.userAgent)

function ShortcutHint() {
  return (
    <p aria-hidden className="text-center text-xs text-grey-600 max-sm:hidden">
      or press{' '}
      <kbd className="rounded border border-grey-300 bg-grey-50 px-1.5 py-0.5 font-sans">
        {IS_MAC ? '⌘' : 'Ctrl'}
      </kbd>{' '}
      +{' '}
      <kbd className="rounded border border-grey-300 bg-grey-50 px-1.5 py-0.5 font-sans">
        Enter
      </kbd>
    </p>
  )
}

interface SuccessProps {
  result: DecisionResult
  onNext: (() => void) | null
}

// After a decision, the next case is one click (or Enter) away (ui.md §2.7).
function Success({ result, onNext }: SuccessProps) {
  const text = result.refunded
    ? 'Refunded and sent'
    : result.action === 'reject'
      ? 'Rejected. The case is back in your review list.'
      : 'Reply sent'
  return (
    <div className="space-y-4">
      <motion.p
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        role="status"
        className="flex items-center gap-2.5 font-medium"
      >
        <span className="icon-tile size-8 bg-success text-white">
          <Check aria-hidden className="size-4" strokeWidth={2.5} />
        </span>
        {text}
      </motion.p>
      {onNext && (
        <button
          type="button"
          autoFocus
          onClick={onNext}
          className="button-primary h-11 w-full"
        >
          Next case
        </button>
      )}
    </div>
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
    <form onSubmit={submit} className="space-y-2 border-t border-grey-100 pt-4">
      <label htmlFor="reject-reason" className="block text-sm font-semibold">
        What's wrong with this suggestion?
      </label>
      <textarea
        id="reject-reason"
        autoFocus
        required
        maxLength={REASON_MAX}
        rows={3}
        value={reason}
        onChange={(event) => setReason(event.target.value)}
        className="field p-2.5"
      />
      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={!valid || pending}
          className="button-primary"
        >
          {pending && (
            <LoaderCircle aria-hidden className="size-4 animate-spin" />
          )}
          {pending ? 'Rejecting…' : 'Reject suggestion'}
        </button>
        <button type="button" onClick={onCancel} className="button-quiet">
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
