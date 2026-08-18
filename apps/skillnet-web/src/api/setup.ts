import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from './client'
import type { WorkspaceMode } from '../types'

export interface SetupStatus {
  initialized: boolean
  /** When false, the SPA does not force the onboarding wizard (testing convenience). */
  onboarding_enabled?: boolean
}

export interface SetupBody {
  workspace_mode: WorkspaceMode
  org_name?: string
  owner_full_name: string
  owner_email: string
  owner_password: string
}

/**
 * Whether this deployment already has an owner. Read once on load to decide
 * whether the first-boot wizard shows. Cached forever within a session — it only
 * flips once, and the mutation invalidates it.
 */
export function useSetupStatus() {
  return useQuery({
    queryKey: ['setup', 'status'],
    queryFn: () => get<SetupStatus>('/setup/status'),
    retry: false,
    staleTime: Infinity,
  })
}

/** Create the owner and set the workspace mode. On success the session cookie is
 *  already set (the endpoint auto-logs the owner in), so `/auth/me` is refetched. */
export function useSubmitSetup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: SetupBody) => post<void>('/setup', body),
    onSuccess: () => {
      queryClient.setQueryData(['setup', 'status'], { initialized: true })
      queryClient.invalidateQueries({ queryKey: ['users', 'me'] })
    },
  })
}
