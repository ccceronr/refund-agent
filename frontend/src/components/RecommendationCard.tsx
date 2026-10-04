// The heart of the page (ui.md §2.3): what to do, who can do it, and why. The tinted top
// and its icon show the kind of outcome at a glance; the headline says it in words.
import {
  Ban,
  Check,
  CircleAlert,
  CircleCheck,
  Eye,
  type LucideIcon,
  MessageSquare,
  ShieldAlert,
  UserCheck,
} from 'lucide-react'
import type { CaseDetail, Proposal } from '../api/types'
import { formatDay, formatTime } from '../lib/format'
import { type VerdictTone, verdictTone } from '../lib/verdict'
import { Checklist } from './Checklist'
import { type OpenPolicy, PolicyQuote } from './PolicyQuote'

const DECISION_VERBS = {
  approve: 'Approved',
  edit: 'Answered',
  reject: 'Rejected',
} as const

const TONES: Record<
  VerdictTone,
  { icon: LucideIcon; head: string; disc: string }
> = {
  refund: { icon: Check, head: 'bg-success/8', disc: 'bg-success text-white' },
  no_refund: { icon: Ban, head: 'bg-navy/5', disc: 'bg-navy text-white' },
  review: {
    icon: Eye,
    head: 'bg-terracotta/10',
    disc: 'bg-terracotta text-navy',
  },
  other: {
    icon: MessageSquare,
    head: 'bg-grey-100',
    disc: 'bg-grey-500 text-white',
  },
}

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
  const tone = TONES[verdictTone(detail.status, proposal.recommendation)]
  const Icon = tone.icon

  return (
    <section aria-labelledby="recommendation" className="card overflow-hidden">
      <div className={`px-6 pt-5 pb-5 ${tone.head}`}>
        <p className="flex items-center gap-2.5">
          <span aria-hidden className={`icon-tile size-8 ${tone.disc}`}>
            <Icon className="size-4" strokeWidth={2.5} />
          </span>
          <span className="label">Recommendation</span>
        </p>
        <h2
          id="recommendation"
          className="mt-3 text-[1.75rem] leading-tight font-medium tracking-tight"
        >
          {proposal.headline}
        </h2>
        {proposal.authority_note && <Authority proposal={proposal} />}
      </div>
      <Reasons detail={detail} onOpenPolicy={onOpenPolicy} />
    </section>
  )
}

// Why, the policy behind it, and who decided. A message that isn't a refund request has
// none of it.
function Reasons({ detail, onOpenPolicy }: RecommendationCardProps) {
  const proposal = detail.proposal
  if (!proposal) return null
  const { manual_reason, checks, policy_quote } = proposal
  if (
    !manual_reason &&
    checks.length === 0 &&
    !policy_quote &&
    !detail.decision
  )
    return null
  return (
    <div className="space-y-5 px-6 py-5">
      {manual_reason ? (
        <p className="flex gap-2.5">
          <CircleAlert
            aria-hidden
            className="mt-1 size-4 shrink-0 text-terracotta"
          />
          <span>{manual_reason}</span>
        </p>
      ) : (
        checks.length > 0 && <Checklist checks={checks} />
      )}
      {policy_quote && (
        <PolicyQuote quote={policy_quote} onOpen={onOpenPolicy} />
      )}
      {detail.decision && (
        <p className="border-t border-grey-100 pt-3 text-sm text-grey-600">
          {DECISION_VERBS[detail.decision.action]} by {detail.decision.by} on{' '}
          {formatDay(detail.decision.at)} at {formatTime(detail.decision.at)}.
        </p>
      )}
    </div>
  )
}

// Who can act on it. Warning text on white is below AA contrast, so the icon carries the
// color and the words stay navy.
const AUTHORITY_ICONS: Record<
  Proposal['tier'],
  { icon: LucideIcon; color: string }
> = {
  AUTO: { icon: CircleCheck, color: 'text-success' },
  STAFF: { icon: UserCheck, color: 'text-success' },
  SUPERVISOR: { icon: ShieldAlert, color: 'text-warning' },
  MANUAL: { icon: UserCheck, color: 'text-grey-600' },
}

function Authority({ proposal }: { proposal: Proposal }) {
  const { icon: Icon, color } = AUTHORITY_ICONS[proposal.tier]
  return (
    <p className="mt-2 flex items-start gap-1.5 text-sm text-grey-700">
      <Icon aria-hidden className={`mt-0.5 size-4 shrink-0 ${color}`} />
      {proposal.authority_note}
    </p>
  )
}

function NotPrepared() {
  return (
    <section className="rounded-2xl border border-dashed border-grey-300 bg-white/60 p-5">
      <p className="label">Recommendation</p>
      <h2 className="mt-1 text-xl font-medium">Not prepared yet</h2>
      <p className="mt-1 text-grey-600">
        The checks, the evidence and a draft reply appear here once the case is
        prepared.
      </p>
    </section>
  )
}
