import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import { declaredReducedMotionContext } from '../../hooks/useReducedMotion'
import { useDynamicCoursesMode } from '../../api/health'
import { useLearnerProfile } from '../../api/onboarding'
import type { UserRole } from '../../types'

const HOME_BY_ROLE: Record<UserRole, string> = {
  admin: '/admin',
  employee: '/empleado',
}

function AppSkeleton() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <img src="/logo.png" alt="SkillNet" className="w-10 h-10 drop-shadow-lg animate-pulse" />
        <div className="h-1.5 w-40 rounded-full bg-white/20 overflow-hidden">
          <div className="h-full w-1/2 rounded-full bg-white/60 animate-pulse" />
        </div>
      </div>
    </div>
  )
}

/**
 * Auth guard, plus the onboarding gate of §6.1.
 *
 * The gate redirects **iff** all three hold:
 *
 *     features.dynamic_courses === 'on'  ∧  user.role === 'employee'
 *     ∧  the profile loaded with onboarding_completed_at == null
 *
 * Each of the four rules below is load-bearing, and this component wraps the admin
 * pages too, so getting any of them wrong breaks a role that has no onboarding:
 *
 * 1. The flag comes from `GET /health`, read once at startup — **not** from
 *    `/auth/me`, which serializes the ORM user and would ship a stale `off`
 *    forever (§10.1).
 * 2. The profile query is **conditioned** on `role === 'employee' && flag === 'on'`,
 *    so an admin never fires it.
 * 3. A **404 means "do not redirect"**, not "not onboarded". `useLearnerProfile`
 *    maps it to `null`. If it meant the latter, turning the flag off mid-session
 *    (the routes become 404) would loop the learner towards a route that no longer
 *    exists.
 * 4. While either query is in flight the skeleton is painted and **nothing is
 *    redirected** — a guess here is a redirect the user has to fight.
 *
 * It is also where the learner's declared `reduce_motion` (§6.2 Q5) is published to
 * the tree. This is the first component with a resolved `/auth/me` and it wraps every
 * authenticated screen including `/onboarding`, so the setting reaches every
 * `useReducedMotion()` below it without any leaf component owning an auth query — and
 * `/login`, which is outside this guard, still fires no extra probe.
 */
export function ProtectedRoute({
  role,
  skipOnboardingGate = false,
  children,
}: {
  role?: UserRole
  /**
   * Set on `/onboarding` itself. Without it the gate would send the wizard to the
   * wizard.
   */
  skipOnboardingGate?: boolean
  children: ReactNode
}) {
  const { user, isLoading } = useAuth()
  const { mode, isLoading: flagLoading } = useDynamicCoursesMode()

  // Rule 2 — conditioned, so this request does not exist for an admin or with the
  // flag off.
  const gateApplies = !skipOnboardingGate && user?.role === 'employee' && mode === 'on'
  const profile = useLearnerProfile({ enabled: gateApplies })

  if (isLoading) return <AppSkeleton />
  if (!user) return <Navigate to="/login" replace />
  if (role && user.role !== role) return <Navigate to={HOME_BY_ROLE[user.role]} replace />

  if (!skipOnboardingGate && user.role === 'employee') {
    // Rule 4 — the flag is still unknown: waiting is correct, guessing is not.
    if (flagLoading) return <AppSkeleton />
    if (gateApplies) {
      if (profile.isLoading) return <AppSkeleton />
      // Rule 3 — `null` is the 404. Only a profile that actually loaded and has no
      // completion timestamp sends anyone anywhere.
      if (profile.data && !profile.data.onboarding_completed_at) {
        return <Navigate to="/onboarding" replace />
      }
    }
  }

  return (
    <declaredReducedMotionContext.Provider value={user.accessibility?.reduce_motion === true}>
      {children}
    </declaredReducedMotionContext.Provider>
  )
}
