// The one page Luis uses (ui.md §2): the navy column with the queue, the open case, and the
// policy panel as a third column when open (it pushes the case aside, never covers it).
// On a narrow screen the three take turns: the list, the case, or the policy (ui.md §2).
import { ArrowLeft } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useCases } from '../api/hooks'
import type { PolicyQuote, Staff } from '../api/types'
import { useSelectedCase } from '../hooks/useSelectedCase'
import { nextCase } from '../lib/queue'
import { CaseView } from './CaseView'
import { ErrorBoundary } from './ErrorBoundary'
import { NoCaseOpen } from './NoCaseOpen'
import { PolicyPanel } from './PolicyPanel'
import { Sidebar } from './Sidebar'

interface OpenPolicy {
  caseId: number
  quote: PolicyQuote
}

export function Workspace({ staff }: { staff: Staff }) {
  const { caseId, select, clear } = useSelectedCase()
  const cases = useCases()
  const next = nextCase(cases.data ?? [], caseId, staff.role)
  const policy = usePolicyPanel(caseId)
  const hidden = (shown: boolean) => (shown ? '' : 'max-lg:hidden')

  return (
    <div className="flex h-dvh">
      <div className={`w-full shrink-0 lg:w-80 ${hidden(caseId === null)}`}>
        <Sidebar
          staff={staff}
          selectedId={caseId}
          onSelect={select}
          onOverview={clear}
        />
      </div>
      <main
        className={`@container relative min-w-0 flex-1 overflow-y-auto ${hidden(caseId !== null && !policy.quote)}`}
      >
        {caseId === null ? (
          <NoCaseOpen
            staff={staff}
            cases={cases.data ?? []}
            next={next}
            onOpen={select}
          />
        ) : (
          <>
            <BackToList onBack={clear} />
            <ErrorBoundary key={caseId}>
              <CaseView
                caseId={caseId}
                role={staff.role}
                onOpenPolicy={policy.open}
                onNext={next ? () => select(next.id) : null}
              />
            </ErrorBoundary>
          </>
        )}
      </main>
      {policy.quote && (
        <PolicyPanel quote={policy.quote} onClose={policy.close} />
      )}
    </div>
  )
}

function BackToList({ onBack }: { onBack: () => void }) {
  return (
    <div className="sticky top-0 z-10 border-b border-navy/8 bg-clay/95 px-4 py-2 backdrop-blur-sm lg:hidden">
      <button type="button" onClick={onBack} className="button-quiet -ml-2">
        <ArrowLeft aria-hidden className="size-4" />
        Back to list
      </button>
    </div>
  )
}

// The panel belongs to the case it was opened from. Closing it puts focus back on the
// quote that opened it, once that quote is visible again (on a narrow screen it was hidden).
function usePolicyPanel(caseId: number | null) {
  const [policy, setPolicy] = useState<OpenPolicy | null>(null)
  const trigger = useRef<HTMLElement | null>(null)
  const restoreFocus = useRef(false)
  const quote = policy && policy.caseId === caseId ? policy.quote : null

  const open = useCallback(
    (opened: PolicyQuote, from: HTMLElement) => {
      if (caseId === null) return
      trigger.current = from
      setPolicy({ caseId, quote: opened })
    },
    [caseId],
  )
  const close = useCallback(() => {
    restoreFocus.current = true
    setPolicy(null)
  }, [])

  useEffect(() => {
    if (quote || !restoreFocus.current) return
    restoreFocus.current = false
    trigger.current?.focus()
  }, [quote])

  return { quote, open, close }
}
