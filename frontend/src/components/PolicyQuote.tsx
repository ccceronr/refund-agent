// An exact passage from the policy, never generated (R-10, LLM09), right under the checks,
// set as a quotation. Its title opens the whole document in the policy panel (ui.md §2.3).
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
    <figure className="border-l-2 border-grey-300 pl-4">
      <blockquote className="leading-relaxed text-grey-700 italic">
        “{quote.text}”
      </blockquote>
      <figcaption className="mt-1.5 text-sm text-grey-600">
        —{' '}
        <button
          type="button"
          onClick={(event) => onOpen(quote, event.currentTarget)}
          className="cursor-pointer font-medium text-terracotta-text underline decoration-[1.5px] underline-offset-4 transition-[text-decoration-color] duration-150 hover:decoration-terracotta-light hover:decoration-[3px]"
        >
          {quote.document}
        </button>
      </figcaption>
    </figure>
  )
}
