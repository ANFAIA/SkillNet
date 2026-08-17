import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import { declaredReducedMotionContext } from '../../hooks/useReducedMotion'
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
        <img src="/logo.png" alt="SkillNet" className="w-10 h-10 drop-shadow-lg motion-safe:animate-pulse motion-reduce:animate-none" />
        <div className="h-1.5 w-40 rounded-full bg-white/20 overflow-hidden">
          <div className="h-full w-1/2 rounded-full bg-white/60 motion-safe:animate-pulse motion-reduce:animate-none" />
        </div>
      </div>
    </div>
  )
}

/**
 * Auth guard, plus the onboarding gate of §6.1.
 *
 * The gate redirects **iff** both hold:
 *
 *     user.role === 'employee'
 *     ∧  the profile loaded with onboarding_completed_at == null
 *
 * Each of the three rules below is load-bearing, and this component wraps the admin
 * pages too, so getting any of them wrong breaks a role that has no onboarding:
 *
 * 1. The profile query is **conditioned** on `role === 'employee'`,
 *    so an admin never fires it.
 * 2. A **404 means "do not redirect"**, not "not onboarded". `useLearnerProfile`
 *    maps it to `null`.
 * 3. While the query is in flight the skeleton is painted and **nothing is
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

  // The onboarding gate applies to every learner: employees always, and — in an
  // `individual` deployment — the admin owner, who also learns and so needs a
  // learner profile. Organization admins never onboard. See audience-modes.md.
  const isIndividualOwner =
    user?.role === 'admin' && user?.workspace_mode === 'individual'
  const gateApplies =
    !skipOnboardingGate && (user?.role === 'employee' || isIndividualOwner)
  const profile = useLearnerProfile({ enabled: gateApplies })

  if (isLoading) return <AppSkeleton />
  if (!user) return <Navigate to="/login" replace />
  if (role && user.role !== role) return <Navigate to={HOME_BY_ROLE[user.role]} replace />

  if (gateApplies) {
    if (profile.isLoading) return <AppSkeleton />
    // Rule 2 — `null` is the 404. Only a profile that actually loaded and has no
    // completion timestamp sends anyone anywhere.
    if (profile.data && !profile.data.onboarding_completed_at) {
      return <Navigate to="/onboarding" replace />
    }
  }

  return (
    <declaredReducedMotionContext.Provider value={user.accessibility?.reduce_motion === true}>
      {children}
    </declaredReducedMotionContext.Provider>
  )
}
