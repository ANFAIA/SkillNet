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

/**
 * `PUT /settings/features` — what the admin switches on and off for their organization.
 *
 * Separate from `useUpdateLlmSettings` because the two have nothing to do with each
 * other: flipping how answers are presented must not require re-entering the API key,
 * which the LLM endpoint would otherwise overwrite with whatever is in the form.
 */
export function useUpdateFeatures() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: { chat_generative_ui: boolean }) =>
      put<OrgSettings>('/settings/features', payload),
    onSuccess: (data) => {
      // Write the server's answer straight into the cache as well as invalidating: the
      // switch is optimistic-looking and a refetch round trip makes it feel sticky.
      queryClient.setQueryData(['organizations', 'me'], data)
      queryClient.invalidateQueries({ queryKey: ['organizations', 'me'] })
    },
  })
}

export function useTestLlm() {
  return useMutation({
    mutationFn: (payload: LlmSettings) => post<LlmTestResult>('/settings/llm/test', payload),
  })
}
