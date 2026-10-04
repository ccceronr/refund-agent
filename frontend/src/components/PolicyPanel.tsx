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
      className="flex w-full shrink-0 flex-col bg-white lg:w-[400px] lg:border-l lg:border-navy/8"
    >
      <div className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-grey-100 pr-3 pl-6">
        <h2
          id="policy-title"
          ref={heading}
          tabIndex={-1}
          className="text-lg font-semibold"
        >
          {policy.data?.title ?? quote.document}
        </h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="button-quiet size-10 px-0"
        >
          <X aria-hidden className="size-5" />
        </button>
      </div>
      <ol className="min-h-0 flex-1 space-y-3 overflow-y-auto px-6 py-5">
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
                  ? 'rounded-xl border-l-[3px] border-terracotta bg-terracotta/10 px-4 py-3'
                  : 'px-4'
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
