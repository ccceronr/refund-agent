// "What happened on Mon, Sep 14": that day's postings in the order the core processed them.
// Every amount and balance carries its sign (+/−), so direction never relies on color.
import { Clock } from 'lucide-react'
import type { Check, Posting } from '../api/types'
import { postingOrderCaption } from '../lib/evidence'
import { formatDay, formatMoney, formatSignedMoney } from '../lib/format'

interface DayTimelineProps {
  day: string
  postings: Posting[]
  checks: Check[]
}

export function DayTimeline({ day, postings, checks }: DayTimelineProps) {
  const caption = postingOrderCaption(postings, checks)
  return (
    <section aria-labelledby="day-timeline" className="card p-6">
      <header className="flex items-center gap-3">
        <span aria-hidden className="icon-tile bg-navy/8 text-navy">
          <Clock className="size-4" />
        </span>
        <div>
          <h2 id="day-timeline" className="font-semibold">
            What happened on {formatDay(day)}
          </h2>
          <p className="text-sm text-grey-600">
            In the order the payments were processed
          </p>
        </div>
      </header>
      <div
        aria-hidden
        className="mt-4 grid grid-cols-[2rem_1fr_auto] gap-x-3 pb-2 text-xs font-medium text-grey-600 max-sm:hidden sm:grid-cols-[2rem_1fr_auto_8.5rem]"
      >
        <span />
        <span>Posting</span>
        <span className="text-right">Amount</span>
        <span className="text-right">Balance after</span>
      </div>
      <ol className="max-sm:mt-4">
        {postings.map((posting, index) => (
          <TimelineRow
            key={posting.order}
            posting={posting}
            last={index === postings.length - 1}
          />
        ))}
      </ol>
      {caption && (
        <p className="mt-3 rounded-xl bg-success/8 px-4 py-3 text-sm">
          {caption}
        </p>
      )}
    </section>
  )
}

function stepColor(posting: Posting): string {
  if (posting.is_fee) return 'bg-terracotta text-navy'
  if (!posting.amount.startsWith('-')) return 'bg-success text-white'
  return 'bg-grey-100 text-navy ring-1 ring-grey-300'
}

function TimelineRow({ posting, last }: { posting: Posting; last: boolean }) {
  const credit = !posting.amount.startsWith('-')
  const overdrawn = posting.balance_after.startsWith('-')
  return (
    <li
      title={posting.raw_description}
      className="relative grid grid-cols-[2rem_1fr_auto] gap-x-3 pb-3 last:pb-0 sm:grid-cols-[2rem_1fr_auto_8.5rem]"
    >
      {!last && (
        <span
          aria-hidden
          className="absolute top-8 bottom-0 left-[15px] w-px bg-grey-200"
        />
      )}
      <span
        aria-hidden
        className={`relative flex size-8 items-center justify-center rounded-full text-sm font-semibold tabular-nums ${stepColor(posting)}`}
      >
        {posting.order}
      </span>
      <span
        className={`self-center rounded-lg ${posting.is_fee ? 'font-semibold' : ''}`}
      >
        <span className="sr-only">{posting.order}. </span>
        {posting.description}
      </span>
      <span
        className={`self-center text-right font-medium tabular-nums ${credit ? 'text-success' : ''}`}
      >
        {formatSignedMoney(posting.amount)}
      </span>
      <span className="self-center text-right max-sm:col-start-2 max-sm:col-end-4 max-sm:text-left">
        <span
          className={`chip tabular-nums ${overdrawn ? 'bg-error/10 text-error' : 'bg-success/10 text-success'}`}
        >
          <span className="sr-only">Balance </span>
          {formatMoney(posting.balance_after)}
        </span>
      </span>
    </li>
  )
}
