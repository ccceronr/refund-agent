// Sends a decision (design §4.3). One Idempotency-Key per user action, kept while that
// same action is retried, so a lost response can never refund twice (R-15).
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useRef } from 'react'
import { apiPost, ApiError } from '../api/client'
import { queryKeys } from '../api/hooks'
import type { DecisionBody } from '../lib/decision'

export interface DecisionResult {
  status: string
  status_label: string
  action: 'approve' | 'edit' | 'reject'
  outcome: 'refund' | 'no_refund' | 'none'
  refunded: boolean
  amount: string | null
}

const NETWORK_RETRIES = 2

function isNetworkError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 0
}

export function useDecision(caseId: number) {
  const client = useQueryClient()
  const pending = useRef<{ body: string; key: string } | null>(null)
  const mutation = useMutation({
    mutationFn: ({ body, key }: { body: DecisionBody; key: string }) =>
      apiPost<DecisionResult>(`/cases/${caseId}/decision`, body, {
        'Idempotency-Key': key,
      }),
    // Same variables, same key: safe to retry when the network failed.
    retry: (failures, error) =>
      failures < NETWORK_RETRIES && isNetworkError(error),
    onSettled: (_data, error) => {
      if (!isNetworkError(error)) pending.current = null
      void client.invalidateQueries({ queryKey: queryKeys.cases })
      void client.invalidateQueries({ queryKey: queryKeys.case(caseId) })
    },
  })

  function decide(body: DecisionBody) {
    const serialized = JSON.stringify(body)
    const key =
      pending.current?.body === serialized
        ? pending.current.key
        : crypto.randomUUID()
    pending.current = { body: serialized, key }
    mutation.mutate({ body, key })
  }

  return {
    decide,
    result: mutation.data,
    error: mutation.error,
    isPending: mutation.isPending,
  }
}
