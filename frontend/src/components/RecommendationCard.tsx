// The heart of the page (ui.md §2.3): what to do, who can do it, why, and the policy.
import { CircleAlert } from 'lucide-react'
import type { CaseDetail } from '../api/types'
import { formatDay, formatTime } from '../lib/format'
import { Checklist } from './Checklist'
import { type OpenPolicy, PolicyQuote } from './PolicyQuote'

const DECISION_VERBS = {
  approve: 'Approved',
  edit: 'Answered',
  reject: 'Rejected',
} as const

interface RecommendationCardProps {
  detail: CaseDetail
  onOpenPolicy: OpenPolicy
}

export function RecommendationCard({
  detail,
  onOpenPolicy,
}: RecommendationCardProps) {
  const proposal = detail.proposal
  if (!proposal) return <NotPrepared />

  return (
    <section
      aria-labelledby="recommendation"
      className="rounded-xl border border-grey-200 bg-white p-6 shadow-sm"
    >
      <p className="text-xs font-semibold tracking-wide text-grey-500 uppercase">
        Recommendation
      </p>
      <h2
        id="recommendation"
        className="mt-1 font-serif text-3xl leading-tight"
      >
        {proposal.headline}
      </h2>
      {proposal.authority_note && (
        <p
          className={
            proposal.tier === 'SUPERVISOR'
              ? 'mt-1 text-warning'
              : 'mt-1 text-grey-600'
          }
        >
          {proposal.authority_note}
        </p>
      )}
      {proposal.manual_reason ? (
        <p className="mt-5 flex gap-2.5">
          <CircleAlert
            aria-hidden
            className="mt-1 size-4 shrink-0 text-terracotta"
          />
          <span>{proposal.manual_reason}</span>
        </p>
      ) : (
        <Checklist checks={proposal.checks} />
      )}
      {proposal.policy_quote && (
        <PolicyQuote quote={proposal.policy_quote} onOpen={onOpenPolicy} />
      )}
      {detail.decision && (
        <p className="mt-5 border-t border-grey-100 pt-4 text-sm text-grey-500">
          {DECISION_VERBS[detail.decision.action]} by {detail.decision.by} on{' '}
          {formatDay(detail.decision.at)} at {formatTime(detail.decision.at)}.
        </p>
      )}
    </section>
  )
}

function NotPrepared() {
  return (
    <section className="rounded-xl border border-dashed border-grey-300 bg-white/60 p-6">
      <p className="text-xs font-semibold tracking-wide text-grey-500 uppercase">
        Recommendation
      </p>
      <h2 className="mt-1 font-serif text-2xl">Not prepared yet</h2>
      <p className="mt-1 text-grey-600">
        The checks, the evidence and a draft reply appear here once the case is
        prepared.
      </p>
    </section>
  )
}
