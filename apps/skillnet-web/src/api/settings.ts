import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post, put } from './client'
import type { LlmTestResult, OrgSettings } from '../types'

export function useSettings() {
  return useQuery({
    queryKey: ['organizations', 'me'],
    queryFn: () => get<OrgSettings>('/settings'),
    staleTime: 5 * 60_000,
  })
}

/**
 * `PUT /settings/features` — what the admin switches on and off for their organization.
 *
 * The only writable thing on this surface. The provider is read-only here: it comes
 * from the deployment's `.env`, because SkillNet runs one organization per deployment
 * and the API key belongs to whoever deployed it. How the product behaves is the
 * admin's call; what it runs on is not.
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

/**
 * `POST /settings/llm/test` — ask the **configured** provider to answer.
 *
 * No payload: there is nothing for the caller to supply, because the provider comes from
 * the deployment's environment. Testing credentials sent in the same request would have
 * tested something other than what the application actually uses.
 */
export function useTestLlm() {
  return useMutation({
    mutationFn: () => post<LlmTestResult>('/settings/llm/test'),
  })
}
