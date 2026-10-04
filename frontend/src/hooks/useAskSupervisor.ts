// Sends a case that's ready for staff to a supervisor (ui.md §2.7, design §4.3a). Safe to
// send twice: once the case waits for a supervisor, the server answers the same.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { apiPost } from '../api/client'
import { queryKeys } from '../api/hooks'

interface Escalation {
  case_id: number
  status: string
  status_label: string
}

export function useAskSupervisor(caseId: number) {
  const client = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => apiPost<Escalation>(`/cases/${caseId}/escalate`),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: queryKeys.cases })
      void client.invalidateQueries({ queryKey: queryKeys.case(caseId) })
    },
  })
  return {
    ask: () => mutation.mutate(),
    error: mutation.error,
    isPending: mutation.isPending,
  }
}
