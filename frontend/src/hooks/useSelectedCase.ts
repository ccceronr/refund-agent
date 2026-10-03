// The open case lives in the URL (?case=5012) so a refresh keeps context (ui.md §4).
import { useCallback, useEffect, useState } from 'react'

const PARAM = 'case'

function readCaseId(): number | null {
  const raw = new URLSearchParams(window.location.search).get(PARAM)
  const id = Number(raw)
  return raw !== null && Number.isInteger(id) && id > 0 ? id : null
}

export function useSelectedCase(): [number | null, (id: number) => void] {
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

  return [caseId, select]
}
