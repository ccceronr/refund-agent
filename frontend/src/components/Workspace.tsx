// The one page Luis uses (ui.md §2): header, queue on the left, the open case on the right.
import type { Staff } from '../api/types'
import { useSelectedCase } from '../hooks/useSelectedCase'
import { CaseView } from './CaseView'
import { Header } from './Header'
import { Queue } from './Queue'

export function Workspace({ staff }: { staff: Staff }) {
  const [caseId, selectCase] = useSelectedCase()

  return (
    <div className="flex min-h-screen flex-col">
      <Header staff={staff} />
      <div className="flex flex-1 flex-col lg:grid lg:grid-cols-[320px_1fr]">
        <Queue role={staff.role} selectedId={caseId} onSelect={selectCase} />
        <main className="min-w-0">
          {caseId === null ? (
            <p className="px-8 py-16 text-center text-grey-500">
              Choose a conversation from the list to see it here.
            </p>
          ) : (
            <CaseView key={caseId} caseId={caseId} role={staff.role} />
          )}
        </main>
      </div>
    </div>
  )
}
