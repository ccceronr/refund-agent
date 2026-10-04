// The whole policy, next to the case (ui.md §2.3): a column that pushes the content aside,
// non-modal (the CSP stays strict), with the quoted passage highlighted. Esc or X closes it.
import { X } from 'lucide-react'
import { motion } from 'motion/react'
import { useEffect, useRef } from 'react'
import { usePolicy } from '../api/hooks'
import type { PolicyQuote } from '../api/types'

interface PolicyPanelProps {
  quote: PolicyQuote
  onClose: () => void
}

export function PolicyPanel({ quote, onClose }: PolicyPanelProps) {
  const policy = usePolicy(quote.slug)
  const heading = useRef<HTMLHeadingElement>(null)
  const highlighted = useRef<HTMLLIElement>(null)

  useEffect(() => {
    heading.current?.focus()
  }, [quote.slug])
  useEffect(() => {
    highlighted.current?.scrollIntoView?.({ block: 'center' })
  }, [policy.data])
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <motion.aside
      aria-labelledby="policy-title"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className="flex flex-col border-t border-grey-200 bg-white lg:sticky lg:top-0 lg:h-[calc(100vh-57px)] lg:border-t-0 lg:border-l"
    >
      <div className="flex items-center justify-between border-b border-grey-100 px-6 py-4">
        <h2
          id="policy-title"
          ref={heading}
          tabIndex={-1}
          className="font-serif text-xl"
        >
          {policy.data?.title ?? quote.document}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="rounded-md p-1 hover:bg-grey-100"
        >
          <X aria-hidden className="size-5" />
        </button>
      </div>
      <ol className="flex-1 space-y-3 overflow-y-auto px-6 py-5">
        {policy.error && (
          <p role="alert" className="text-error">
            {policy.error.message}
          </p>
        )}
        {policy.data?.passages.map((passage) => {
          const quoted = passage.id === quote.passage_id
          return (
            <li
              key={passage.id}
              ref={quoted ? highlighted : undefined}
              aria-current={quoted ? 'true' : undefined}
              className={
                quoted
                  ? 'rounded-md border-l-2 border-terracotta bg-terracotta/8 px-3 py-2'
                  : 'px-3'
              }
            >
              {passage.text}
            </li>
          )
        })}
      </ol>
    </motion.aside>
  )
}
