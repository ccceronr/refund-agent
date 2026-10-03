// Server state (ui.md §4): ['cases'] and ['case', id], plus the signed-in staff member.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiGet, apiPost, isSignedOut } from './client'
import type { CaseDetail, CaseListItem, PolicyDocument, Staff } from './types'

export const queryKeys = {
  me: ['me'] as const,
  cases: ['cases'] as const,
  case: (id: number) => ['case', id] as const,
  policy: (slug: string) => ['policy', slug] as const,
}

async function fetchMe(): Promise<Staff | null> {
  try {
    return await apiGet<Staff>('/auth/me')
  } catch (error) {
    if (isSignedOut(error)) return null
    throw error
  }
}

export function useMe() {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: fetchMe,
    staleTime: Infinity,
  })
}

export function useSignIn() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (credentials: { username: string; password: string }) =>
      apiPost<Staff>('/auth/login', credentials),
    onSuccess: (staff) => {
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== 'me' })
      client.setQueryData(queryKeys.me, staff)
    },
  })
}

export function useSignOut() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => apiPost<void>('/auth/logout'),
    onSettled: () => {
      client.clear()
      client.setQueryData(queryKeys.me, null)
    },
  })
}

export function useCases() {
  return useQuery({
    queryKey: queryKeys.cases,
    queryFn: () => apiGet<CaseListItem[]>('/cases'),
  })
}

export function useCase(id: number | null) {
  return useQuery({
    queryKey: queryKeys.case(id ?? 0),
    queryFn: () => apiGet<CaseDetail>(`/cases/${id}`),
    enabled: id !== null,
  })
}

export function usePolicy(slug: string | null) {
  return useQuery({
    queryKey: queryKeys.policy(slug ?? ''),
    queryFn: () => apiGet<PolicyDocument>(`/policies/${slug}`),
    enabled: slug !== null,
    staleTime: Infinity,
  })
}
