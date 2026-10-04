// The one page Luis uses (ui.md §2): header, queue on the left, the open case, and the
// policy panel as a third column when open (it pushes the case aside, never covers it).
import { useCallback, useRef, useState } from 'react'
import type { PolicyQuote, Staff } from '../api/types'
import { useSelectedCase } from '../hooks/useSelectedCase'
import { CaseView } from './CaseView'
import { ErrorBoundary } from './ErrorBoundary'
import { Header } from './Header'
import { PolicyPanel } from './PolicyPanel'
import { Queue } from './Queue'

interface OpenPolicy {
  caseId: number
  quote: PolicyQuote
}

export function Workspace({ staff }: { staff: Staff }) {
  const [caseId, selectCase] = useSelectedCase()
  const [policy, setPolicy] = useState<OpenPolicy | null>(null)
  const trigger = useRef<HTMLElement | null>(null)
  // The panel belongs to the case it was opened from.
  const shownPolicy = policy && policy.caseId === caseId ? policy.quote : null

  const openPolicy = useCallback(
    (quote: PolicyQuote, from: HTMLElement) => {
      if (caseId === null) return
      trigger.current = from
      setPolicy({ caseId, quote })
    },
    [caseId],
  )
  const closePolicy = useCallback(() => {
    setPolicy(null)
    trigger.current?.focus()
  }, [])

  return (
    <div className="flex min-h-screen flex-col">
      <Header staff={staff} />
      <div
        className={`flex flex-1 flex-col lg:grid ${
          shownPolicy
            ? 'lg:grid-cols-[320px_1fr_380px]'
            : 'lg:grid-cols-[320px_1fr]'
        }`}
      >
        <Queue role={staff.role} selectedId={caseId} onSelect={selectCase} />
        <main className="min-w-0">
          {caseId === null ? (
            <p className="px-8 py-16 text-center text-grey-500">
              Choose a conversation from the list to see it here.
            </p>
          ) : (
            <ErrorBoundary key={caseId}>
              <CaseView
                caseId={caseId}
                role={staff.role}
                onOpenPolicy={openPolicy}
              />
            </ErrorBoundary>
          )}
        </main>
        {shownPolicy && (
          <PolicyPanel quote={shownPolicy} onClose={closePolicy} />
        )}
      </div>
    </div>
  )
}
