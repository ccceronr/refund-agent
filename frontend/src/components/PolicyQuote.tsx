// An exact passage from the policy, never generated (R-10, LLM09). Its title opens the
// whole document in the policy panel (ui.md §2.3).
import type { PolicyQuote as Quote } from '../api/types'

export type OpenPolicy = (quote: Quote, trigger: HTMLElement) => void

export function PolicyQuote({
  quote,
  onOpen,
}: {
  quote: Quote
  onOpen: OpenPolicy
}) {
  return (
    <figure className="mt-6 border-l-2 border-grey-200 pl-4">
      <blockquote className="font-serif text-lg text-grey-700 italic">
        “{quote.text}”
      </blockquote>
      <figcaption className="mt-1 text-sm text-grey-500">
        —{' '}
        <button
          type="button"
          onClick={(event) => onOpen(quote, event.currentTarget)}
          className="underline decoration-grey-300 underline-offset-2 hover:text-navy"
        >
          {quote.document}
        </button>
      </figcaption>
    </figure>
  )
}
