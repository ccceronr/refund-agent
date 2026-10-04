// Runs the flow for one case and follows its steps live (R-03, R-16; design §4.4).
import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { queryKeys } from '../api/hooks'
import { postStream } from '../api/stream'
import type { CaseDetail } from '../api/types'
import { applyStepEvent, type StepEvent, type StepProgress } from '../lib/run'

export interface RunState {
  phase: 'idle' | 'running' | 'failed'
  steps: StepProgress[]
  message: string | null
}

const IDLE: RunState = { phase: 'idle', steps: [], message: null }

export function useCaseRun(caseId: number): [RunState, () => void] {
  const client = useQueryClient()
  const [state, setState] = useState<RunState>(IDLE)
  const abort = useRef<AbortController | null>(null)

  // Leaving the page stops listening; the run itself finishes on the server.
  useEffect(() => () => abort.current?.abort(), [])

  const start = useCallback(() => {
    const controller = new AbortController()
    abort.current = controller
    setState({ phase: 'running', steps: [], message: null })
    let claimed = false
    const onEvent = (name: string, data: unknown) => {
      if (name === 'step') {
        // The first step means the server claimed the case: the queue shows "Preparing…".
        if (!claimed) {
          claimed = true
          void client.invalidateQueries({ queryKey: queryKeys.cases })
        }
        setState((current) => ({
          ...current,
          steps: applyStepEvent(current.steps, data as StepEvent),
        }))
      } else if (name === 'completed') {
        client.setQueryData(queryKeys.case(caseId), data as CaseDetail)
        setState(IDLE)
      } else if (name === 'failed') {
        const { message } = data as { message: string }
        setState((current) => ({ ...current, phase: 'failed', message }))
      }
    }
    postStream(`/cases/${caseId}/run`, onEvent, controller.signal)
      .catch((error: Error) =>
        setState((current) => ({
          ...current,
          phase: 'failed',
          message: error.message,
        })),
      )
      .finally(() => {
        void client.invalidateQueries({ queryKey: queryKeys.cases })
        void client.invalidateQueries({ queryKey: queryKeys.case(caseId) })
      })
  }, [caseId, client])

  return [state, start]
}
