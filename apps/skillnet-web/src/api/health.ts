/**
 * `GET /health` — the **only** place the dynamic-courses flag is exposed (§10.1).
 *
 * Not `/auth/me`: that route serializes the ORM user through `UserRead`, which has
 * no `features` column, so the field would either raise on every call or serialize
 * a stale default forever — the frontend reading `"off"` for eternity with the flag
 * on. The spec closes that door explicitly, so this is a separate, public query.
 *
 * Read **once at startup**: `staleTime: Infinity` plus no refetch on focus or
 * mount. A feature flag that flips mid-session is an operator action, not
 * something the client should poll for; and the gate in `ProtectedRoute` reads
 * this value on every protected render, so a refetching query would turn a
 * deploy-time toggle into a redirect flicker.
 */

import { useQuery } from '@tanstack/react-query'
import { get } from './client'

export type DynamicCoursesMode = 'off' | 'shadow' | 'on'

export interface HealthRead {
  status: string
  version: string
  database: string
  features?: {
    dynamic_courses?: DynamicCoursesMode
  }
}

export const healthKey = ['health'] as const

export function useHealth() {
  return useQuery({
    queryKey: healthKey,
    queryFn: () => get<HealthRead>('/health'),
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
  })
}

/**
 * The flag, plus whether it is still unknown.
 *
 * An unreachable or malformed `/health` reads as `off`: with the flag unknown the
 * v2 surfaces stay hidden instead of half-mounted. Callers that must not act on a
 * guess (the onboarding gate) check `isLoading` first and wait.
 */
export function useDynamicCoursesMode(): {
  mode: DynamicCoursesMode
  isLoading: boolean
} {
  const { data, isLoading } = useHealth()
  return { mode: data?.features?.dynamic_courses ?? 'off', isLoading }
}
