// An exact passage from the policy, never generated (R-10, LLM09). The side sheet with
// the whole document arrives with the dialogs in P7b.
import type { PolicyQuote as Quote } from '../api/types'

export function PolicyQuote({ quote }: { quote: Quote }) {
  return (
    <figure className="mt-6 border-l-2 border-grey-200 pl-4">
      <blockquote className="font-serif text-lg text-grey-700 italic">
        “{quote.text}”
      </blockquote>
      <figcaption className="mt-1 text-sm text-grey-500">
        — {quote.document}
      </figcaption>
    </figure>
  )
}
