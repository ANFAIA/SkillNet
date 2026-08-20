import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from './client'
import type { WorkspaceMode } from '../types'

/**
 * Capability flags — the single source of truth for "según lo que hay disponible,
 * muestra una cosa u otra" (docs/design/onboarding.md §2.1). Derived on the backend
 * from the presence/validity of keys and exposed on the setup-status payload.
 */
export interface Capabilities {
  /** A usable LLM exists — nothing AI works without this. */
  ai: boolean
  /** Generate courses / lessons. */
  generation: boolean
  /** Tutor chat. */
  tutor: boolean
  /** Voice (mascot / podcast) — degrades to offline, see degraded-mode-ux. */
  tts: boolean
  /** Infographics. */
  images: boolean
}

/**
 * Safe defaults when the backend has not (yet) sent a `capabilities` field — for
 * example an older API, or the field still landing. We default to *available* so a
 * capability is never hidden unexpectedly (docs/design/onboarding.md §2.2: the AI
 * side is additive; a missing signal must not silently strip UI that used to work).
 */
export const DEFAULT_CAPABILITIES: Capabilities = {
  ai: true,
  generation: true,
  tutor: true,
  tts: true,
  images: true,
}

export interface SetupStatus {
  initialized: boolean
  /** When false, the SPA does not force the onboarding wizard (testing convenience). */
  onboarding_enabled?: boolean
  /**
   * Capability flags (§2.1). Optional: an older backend, or the field still landing,
   * leaves it undefined — consumers fall back to {@link DEFAULT_CAPABILITIES}.
   */
  capabilities?: Capabilities
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

/**
 * The deployment's capabilities (docs/design/onboarding.md §2.1). Reads the same
 * setup-status query — the backend puts `capabilities` on that payload — so this is
 * the one place any AI-aware piece asks "what's available?"; nobody hardcodes "hay
 * clave". Falls back to {@link DEFAULT_CAPABILITIES} until the field is present.
 */
export function useCapabilities(): Capabilities {
  const { data } = useSetupStatus()
  return data?.capabilities ?? DEFAULT_CAPABILITIES
}

/** A single capability flag (§2.2). Convenience over {@link useCapabilities}. */
export function useCapability(name: keyof Capabilities): boolean {
  return useCapabilities()[name]
}

/** Create the owner and set the workspace mode. On success the session cookie is
 *  already set (the endpoint auto-logs the owner in), so `/auth/me` is refetched. */
export function useSubmitSetup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: SetupBody) => post<void>('/setup', body),
    onSuccess: () => {
      // Merge, don't replace: setup only flips `initialized`. Blowing away the whole
      // object here would drop `onboarding_enabled` and `capabilities` until the next
      // fetch, briefly re-forcing the wizard / hiding AI UI. Preserve what we had.
      queryClient.setQueryData<SetupStatus>(['setup', 'status'], (prev) => ({
        ...(prev ?? {}),
        initialized: true,
      }))
      queryClient.invalidateQueries({ queryKey: ['users', 'me'] })
    },
  })
}
