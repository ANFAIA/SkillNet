import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post, put } from './client'
import type { LlmSettings, LlmTestResult, OrgSettings } from '../types'

export function useSettings() {
  return useQuery({
    queryKey: ['organizations', 'me'],
    queryFn: () => get<OrgSettings>('/settings'),
    staleTime: 5 * 60_000,
  })
}

export function useUpdateLlmSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: LlmSettings) => put<OrgSettings>('/settings/llm', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['organizations', 'me'] })
    },
  })
}

export function useTestLlm() {
  return useMutation({
    mutationFn: (payload: LlmSettings) => post<LlmTestResult>('/settings/llm/test', payload),
  })
}
