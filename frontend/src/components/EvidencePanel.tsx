// The evidence (ui.md §2.4), open so Luis can check it at a glance: the day in posting
// order, then the fee, the refunds used, the standing and the account. The account card
// is the only place the full account number is shown (R-33).
import {
  History,
  Landmark,
  type LucideIcon,
  Receipt,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react'
import type { ReactNode } from 'react'
import type { Evidence, FeeChoice, Member, Proposal } from '../api/types'
import { formatDay, formatMoney } from '../lib/format'
import { DayTimeline } from './DayTimeline'

interface EvidencePanelProps {
  evidence: Evidence
  proposal: Proposal | null
  standing: Member['standing']
}

export function EvidencePanel({
  evidence,
  proposal,
  standing,
}: EvidencePanelProps) {
  const fee = evidence.fee
  return (
    <section aria-label="Evidence" className="space-y-4">
      {fee && evidence.day_postings.length > 0 && (
        <DayTimeline
          day={fee.date}
          postings={evidence.day_postings}
          checks={proposal?.checks ?? []}
        />
      )}
      <ul className="grid gap-4 @xl:grid-cols-2">
        {fee && (
          <Fact icon={Receipt} tint="bg-terracotta/14" title="Fee charged">
            <Value>{formatMoney(fee.amount.replace('-', ''))}</Value>
            <Note>
              {fee.label} · {formatDay(fee.date)}
            </Note>
          </Fact>
        )}
        <RefundsUsed evidence={evidence} />
        <Standing standing={standing} />
        {fee && (
          <Fact icon={Landmark} tint="bg-navy/8" title="Account">
            <Value>{fee.sub_account}</Value>
            <Note>
              <span className="tabular-nums">{fee.account_number_full}</span>
            </Note>
          </Fact>
        )}
      </ul>
      <RecentFees fees={proposal?.fee_choices ?? []} />
    </section>
  )
}

interface FactProps {
  icon: LucideIcon
  tint: string
  title: string
  children: ReactNode
}

function Fact({ icon: Icon, tint, title, children }: FactProps) {
  return (
    <li className="card flex gap-4 p-5">
      <span aria-hidden className={`icon-tile size-10 text-navy ${tint}`}>
        <Icon className="size-[18px]" />
      </span>
      <div className="min-w-0 flex-1">
        <h3 className="label">{title}</h3>
        {children}
      </div>
    </li>
  )
}

function Value({ children }: { children: ReactNode }) {
  return (
    <p className="text-lg leading-snug font-semibold tabular-nums">
      {children}
    </p>
  )
}

function Note({ children }: { children: ReactNode }) {
  return <p className="text-sm text-grey-600">{children}</p>
}

function RefundsUsed({ evidence }: { evidence: Evidence }) {
  const used = evidence.refunds_used ?? evidence.refund_history.length
  return (
    <Fact icon={History} tint="bg-navy/8" title="Refunds in the last 12 months">
      <div className="flex items-center gap-3">
        <Value>
          {used} of {evidence.refunds_limit}
        </Value>
        <RefundMeter used={used} limit={evidence.refunds_limit} />
      </div>
      {evidence.refund_history.length > 0 ? (
        <ul className="mt-1 space-y-0.5 text-sm text-grey-600">
          {evidence.refund_history.map((refund) => (
            <li
              key={`${refund.date}-${refund.amount}`}
              className="flex justify-between gap-3"
            >
              <span>
                {formatDay(refund.date)} · {refund.label}
              </span>
              <span className="tabular-nums">{formatMoney(refund.amount)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <Note>No refunds yet</Note>
      )}
    </Fact>
  )
}

// One segment per refund allowed; the words next to it say the same (never color alone).
function RefundMeter({ used, limit }: { used: number; limit: number }) {
  return (
    <span aria-hidden className="flex gap-1">
      {Array.from({ length: limit }, (_, slot) => (
        <span
          key={slot}
          className={`h-2 w-5 rounded-full ${slot < used ? 'bg-terracotta' : 'bg-grey-200'}`}
        />
      ))}
    </span>
  )
}

function Standing({ standing }: { standing: Member['standing'] }) {
  const good = standing === 'good'
  return (
    <Fact
      icon={good ? ShieldCheck : ShieldAlert}
      tint={good ? 'bg-success/12' : 'bg-error/10'}
      title="Standing"
    >
      <Value>{good ? 'In good standing' : 'Not in good standing'}</Value>
    </Fact>
  )
}

function RecentFees({ fees }: { fees: FeeChoice[] }) {
  if (fees.length === 0) return null
  return (
    <div className="card p-5">
      <h3 className="label">Recent fees</h3>
      <ul className="mt-1.5 space-y-1">
        {fees.map((fee) => (
          <li key={fee.id}>{fee.label}</li>
        ))}
      </ul>
    </div>
  )
}
