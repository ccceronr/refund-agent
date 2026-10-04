// The open case lives in the URL (?case=5012) so a refresh keeps context (ui.md §4).
import { useCallback, useEffect, useState } from 'react'

const PARAM = 'case'

function readCaseId(): number | null {
  const raw = new URLSearchParams(window.location.search).get(PARAM)
  const id = Number(raw)
  return raw !== null && Number.isInteger(id) && id > 0 ? id : null
}

interface SelectedCase {
  caseId: number | null
  select: (id: number) => void
  // On a narrow screen the list and the case take turns: this goes back to the list.
  clear: () => void
}

export function useSelectedCase(): SelectedCase {
  const [caseId, setCaseId] = useState(readCaseId)

  useEffect(() => {
    const onHistoryChange = () => setCaseId(readCaseId())
    window.addEventListener('popstate', onHistoryChange)
    return () => window.removeEventListener('popstate', onHistoryChange)
  }, [])

  const select = useCallback((id: number) => {
    const url = new URL(window.location.href)
    url.searchParams.set(PARAM, String(id))
    window.history.pushState(null, '', url)
    setCaseId(id)
  }, [])

  const clear = useCallback(() => {
    const url = new URL(window.location.href)
    url.searchParams.delete(PARAM)
    window.history.pushState(null, '', url)
    setCaseId(null)
  }, [])

  return { caseId, select, clear }
}
