// "Prepare new messages" (R-03, ui.md §2.1): every new case, one by one, on the server.
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { queryKeys } from '../api/hooks'
import { postStream } from '../api/stream'

interface CaseProgress {
  index: number
  total: number
  case_id: number
  member_name: string
  status: string
}

export interface PrepareState {
  phase: 'idle' | 'running' | 'done' | 'failed'
  current: CaseProgress | null
  summary: string | null
}

const IDLE: PrepareState = { phase: 'idle', current: null, summary: null }

export function usePrepareNew(): [PrepareState, () => void] {
  const client = useQueryClient()
  const [state, setState] = useState<PrepareState>(IDLE)
  const abort = useRef<AbortController | null>(null)

  useEffect(() => () => abort.current?.abort(), [])

  const start = useCallback(() => {
    const controller = new AbortController()
    abort.current = controller
    setState({ phase: 'running', current: null, summary: null })
    const onEvent = (name: string, data: unknown) => {
      if (name === 'case') {
        const progress = data as CaseProgress
        setState((current) => ({ ...current, current: progress }))
        // Each case moves to its section as soon as it is ready.
        if (progress.status !== 'running') {
          void client.invalidateQueries({ queryKey: queryKeys.cases })
          void client.invalidateQueries({
            queryKey: queryKeys.case(progress.case_id),
          })
        }
      } else if (name === 'done') {
        const { prepared, skipped } = data as {
          prepared: number
          skipped: number
        }
        const summary = skipped
          ? `${prepared} prepared, ${skipped} skipped`
          : `${prepared} prepared`
        setState({ phase: 'done', current: null, summary })
      } else if (name === 'failed') {
        setState({
          phase: 'failed',
          current: null,
          summary: (data as { message: string }).message,
        })
      }
    }
    postStream('/cases/prepare-new', onEvent, controller.signal)
      .catch((error: Error) =>
        setState({ phase: 'failed', current: null, summary: error.message }),
      )
      .finally(
        () => void client.invalidateQueries({ queryKey: queryKeys.cases }),
      )
  }, [client])

  return [state, start]
}
