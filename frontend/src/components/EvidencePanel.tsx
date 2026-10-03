// The evidence, collapsed by default (ui.md §2.4): the day in posting order, the refunds
// used, and the account. The only place the full account number is shown (R-33).
import { ChevronRight } from 'lucide-react'
import { Collapsible } from 'radix-ui'
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
    <Collapsible.Root>
      <Collapsible.Trigger className="group flex items-center gap-1.5 font-medium text-navy hover:text-terracotta">
        <ChevronRight
          aria-hidden
          className="size-4 transition-transform duration-200 group-data-[state=open]:rotate-90"
        />
        See the evidence
      </Collapsible.Trigger>
      <Collapsible.Content className="mt-4 space-y-6 rounded-xl border border-grey-200 bg-white p-6">
        {fee && evidence.day_postings.length > 0 && (
          <DayTimeline
            day={fee.date}
            postings={evidence.day_postings}
            checks={proposal?.checks ?? []}
          />
        )}
        <RecentFees fees={proposal?.fee_choices ?? []} />
        <RefundHistory evidence={evidence} />
        {fee && (
          <section>
            <h3 className="font-semibold">Account</h3>
            <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
              <dt className="text-grey-500">Account</dt>
              <dd>{fee.sub_account}</dd>
              <dt className="text-grey-500">Account number</dt>
              <dd className="tabular-nums">{fee.account_number_full}</dd>
              <dt className="text-grey-500">Standing</dt>
              <dd>
                {standing === 'good'
                  ? 'In good standing'
                  : 'Not in good standing'}
              </dd>
            </dl>
          </section>
        )}
      </Collapsible.Content>
    </Collapsible.Root>
  )
}

function RecentFees({ fees }: { fees: FeeChoice[] }) {
  if (fees.length === 0) return null
  return (
    <section>
      <h3 className="font-semibold">Recent fees</h3>
      <ul className="mt-2 space-y-1 text-sm">
        {fees.map((fee) => (
          <li key={fee.id}>{fee.label}</li>
        ))}
      </ul>
    </section>
  )
}

function RefundHistory({ evidence }: { evidence: Evidence }) {
  const used = evidence.refunds_used ?? evidence.refund_history.length
  return (
    <section>
      <h3 className="font-semibold">Refunds in the last 12 months</h3>
      <p className="text-sm text-grey-600">
        {used} of {evidence.refunds_limit} used
      </p>
      {evidence.refund_history.length > 0 && (
        <ul className="mt-2 space-y-1 text-sm">
          {evidence.refund_history.map((refund) => (
            <li
              key={`${refund.date}-${refund.amount}`}
              className="flex justify-between gap-4"
            >
              <span>
                {formatDay(refund.date)} · {refund.label}
              </span>
              <span className="tabular-nums">{formatMoney(refund.amount)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
