// "What happened on Mon, Sep 14": that day's postings in the order the core processed them.
import type { Check, Posting } from '../api/types'
import { postingOrderCaption } from '../lib/evidence'
import { formatDay, formatMoney } from '../lib/format'

interface DayTimelineProps {
  day: string
  postings: Posting[]
  checks: Check[]
}

export function DayTimeline({ day, postings, checks }: DayTimelineProps) {
  const caption = postingOrderCaption(postings, checks)
  return (
    <section>
      <h3 className="font-semibold">What happened on {formatDay(day)}</h3>
      <ol className="mt-3 border-l border-grey-200">
        {postings.map((posting) => (
          <li
            key={posting.order}
            title={posting.raw_description}
            className={`relative -ml-px grid grid-cols-[1fr_auto_auto] gap-4 border-l-2 py-1.5 pr-2 pl-4 text-sm ${
              posting.is_fee
                ? 'border-terracotta bg-terracotta/8'
                : 'border-transparent'
            }`}
          >
            <span>
              <span className="text-grey-400 tabular-nums">
                {posting.order}.
              </span>{' '}
              {posting.description}
            </span>
            <span className="text-right tabular-nums">
              {formatMoney(posting.amount)}
            </span>
            <span className="w-36 text-right text-grey-500 tabular-nums">
              balance {formatMoney(posting.balance_after)}
            </span>
          </li>
        ))}
      </ol>
      {caption && <p className="mt-3 text-sm text-grey-600">{caption}</p>}
    </section>
  )
}
