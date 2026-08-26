import { useMemo } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from './client'
import type { MediaKind } from './media'
import type { WorkspaceMode } from '../types'

/**
 * How a capability is doing right now.
 *
 * * `ready`    — fully usable.
 * * `degraded` — usable, but reduced: the offline robotic voice instead of a natural
 *   one, an infographic without its poster. The UI stays; it just does less.
 * * `blocked`  — not usable at all. A control that needs it must never fire a job.
 */
export type CapabilityStatus = 'ready' | 'degraded' | 'blocked'

/** Why a capability is not `ready`. Machine-readable; the sentence is written here. */
export type CapabilityReason =
  | 'missing_api_key'
  | 'not_configured'
  | 'provider_quota'
  | 'provider_down'

export interface Capability {
  status: CapabilityStatus
  reason?: CapabilityReason | null
  /**
   * Admin-only English detail from the backend. **Always null on the public
   * `/setup/status` payload** — it only arrives on the authenticated admin endpoint —
   * so never rely on it being present, and never render it to a non-admin.
   */
  hint?: string | null
}

/**
 * Capability status — the single source of truth for "según lo que hay disponible,
 * muestra una cosa u otra" (docs/design/onboarding.md §2.1). Derived on the backend
 * from the presence/validity of keys and exposed on the setup-status payload.
 *
 * Every entry is an object, not a boolean: "off" was never the whole story — a
 * learner clicking a dead control deserves to know *why*, and an admin deserves to
 * know *what to do*. See {@link Capability}.
 */
export interface Capabilities {
  /** A usable LLM exists — nothing AI works without this. */
  ai: Capability
  /** Generate courses / lessons. */
  generation: Capability
  /** Tutor chat. */
  tutor: Capability
  /** Voice (mascot / podcast) — degrades to offline, see degraded-mode-ux. */
  tts: Capability
  /** Infographics. */
  images: Capability
  /**
   * "Sign in with Google" is configured on the backend. Not an AI capability, but it
   * travels on the same public, pre-authentication payload the login screen already
   * reads, which is the only channel available before anyone has a session.
   *
   * Optional, like the payload it rides on: a backend from before this feature sends
   * `capabilities` without it, and `useCapabilities` fills the gap from the defaults
   * below rather than letting `undefined` reach a consumer.
   */
  google_login?: Capability
}

/** A capability's key. Used wherever a control declares what it needs. */
export type CapabilityName = keyof Capabilities

/**
 * Which capabilities each media kind needs before its job can succeed. Sent by the
 * backend on the setup-status payload so the table lives in exactly one place — the
 * web app must not carry its own copy, or the two drift and a learner clicks a
 * control that dies thirty seconds later.
 *
 * A kind the backend does not mention has no known requirement, which reads as
 * "available" (same policy as {@link DEFAULT_CAPABILITIES}).
 */
export type MediaRequirements = Partial<Record<MediaKind, CapabilityName[]>>

/**
 * Safe defaults when the backend has not (yet) sent a `capabilities` field — for
 * example an older API, or the field still landing. We default to *available* so a
 * capability is never hidden unexpectedly (docs/design/onboarding.md §2.2: the AI
 * side is additive; a missing signal must not silently strip UI that used to work).
 */
export const DEFAULT_CAPABILITIES: Required<Capabilities> = {
  ai: { status: 'ready' },
  generation: { status: 'ready' },
  tutor: { status: 'ready' },
  tts: { status: 'ready' },
  images: { status: 'ready' },
  // The one entry that defaults to blocked, deliberately breaking the "default to
  // available" rule above. That rule protects UI that used to work; this is a button
  // that leads straight to a 404 unless the backend really does have Google
  // credentials, so the safe fallback is the opposite one.
  google_login: { status: 'blocked', reason: 'not_configured' },
}

const CAPABILITY_STATUSES: CapabilityStatus[] = ['ready', 'degraded', 'blocked']

/**
 * Coerce whatever arrived into a {@link Capability}.
 *
 * The wire shape changed from `boolean` to an object, and a deployment can run a
 * frontend that is newer than its API for as long as its next `docker compose pull`
 * takes. A boolean therefore still has to mean something sane: `true` is `ready`,
 * `false` is `blocked` with no reason we can name — which is exactly what the old UI
 * conveyed, only now the explain path has something to hang on.
 */
export function normalizeCapability(value: unknown, fallback: Capability): Capability {
  if (value === true) return { status: 'ready' }
  if (value === false) return { status: 'blocked' }
  if (!value || typeof value !== 'object') return fallback
  const raw = value as Partial<Capability>
  const status = CAPABILITY_STATUSES.includes(raw.status as CapabilityStatus)
    ? (raw.status as CapabilityStatus)
    // An unrecognised status is a newer backend saying something we cannot read.
    // Fall back to the documented "unknown ⇒ available" rule rather than to a lie.
    : fallback.status
  return { status, reason: raw.reason ?? null, hint: raw.hint ?? null }
}

/** Fully usable. The bar a control must clear before it may fire a job. */
export function isReady(capability: Capability | undefined): boolean {
  return capability?.status === 'ready'
}

/** Usable at all — `degraded` still counts. The bar for *showing* a control. */
export function isAvailable(capability: Capability | undefined): boolean {
  return capability !== undefined && capability.status !== 'blocked'
}

export interface SetupStatus {
  initialized: boolean
  /** When false, the SPA does not force the onboarding wizard (testing convenience). */
  onboarding_enabled?: boolean
  /**
   * Capability status (§2.1). Optional: an older backend, or the field still landing,
   * leaves it undefined — consumers fall back to {@link DEFAULT_CAPABILITIES}.
   */
  capabilities?: Capabilities
  /**
   * Which capabilities each media kind needs (see {@link MediaRequirements}).
   * Optional for the same reason: an older backend omits it, and an absent table
   * constrains nothing.
   */
  media_requirements?: MediaRequirements
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
export function useCapabilities(): Required<Capabilities> {
  const { data } = useSetupStatus()
  const raw = data?.capabilities
  // Memoized on the payload, not rebuilt per render: consumers put this object in
  // `useMemo`/`useEffect` deps, and a fresh literal every render defeats all of them.
  return useMemo(() => {
    const merged = {} as Required<Capabilities>
    for (const name of Object.keys(DEFAULT_CAPABILITIES) as CapabilityName[]) {
      merged[name] = normalizeCapability(
        (raw as Record<string, unknown> | undefined)?.[name],
        DEFAULT_CAPABILITIES[name],
      )
    }
    return merged
  }, [raw])
}

/** A single capability (§2.2). Convenience over {@link useCapabilities}. */
export function useCapability(name: CapabilityName): Capability {
  return useCapabilities()[name]
}

/** Stable identity so `useMediaRequirements()` is safe in dependency arrays. */
const EMPTY_REQUIREMENTS: MediaRequirements = {}

/**
 * The media-kind → required-capabilities table from the backend. Empty until the
 * field lands, which constrains nothing — no kind is gated on a table we never got.
 */
export function useMediaRequirements(): MediaRequirements {
  const { data } = useSetupStatus()
  return data?.media_requirements ?? EMPTY_REQUIREMENTS
}

/**
 * Flatten to plain booleans for the few places that only ask "is it there?" — the
 * tour's step filter, which takes a boolean map and should not learn about statuses.
 * `degraded` counts as there: a reduced feature is still a feature.
 */
export function readyFlags(capabilities: Capabilities): Record<string, boolean> {
  const flags: Record<string, boolean> = {}
  for (const [name, capability] of Object.entries(capabilities)) {
    flags[name] = isAvailable(capability as Capability)
  }
  return flags
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
