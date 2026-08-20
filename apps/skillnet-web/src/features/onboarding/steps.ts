import type { OnboardingStep } from './types'

/**
 * The employee product tour (docs/design/onboarding.md §3.1, Fase 0). Pure data:
 * each step points at a stable `[data-tour]` anchor on the redesigned employee home
 * (`/empleado`, `pages/employee/Dashboard.tsx`) and the copy is i18n ids.
 *
 * Shape: encuadre → recorrido de la casa → "abre tu primera lección". The last step
 * lands back on the start/continue hero CTA, the single action that opens the first
 * pre-generated lesson — value by doing, not a manual.
 *
 * Fase 1/2 extend this list (contrast nudge, tutor step with `requires`); nothing
 * here needs to change for that — a new capability-gated step is one more object.
 */
export const employeeTourSteps: OnboardingStep[] = [
  {
    id: 'welcome',
    role: 'employee',
    target: '[data-tour="home-hero"]',
    title: 'onboarding.tour.welcome.title',
    body: 'onboarding.tour.welcome.body',
    order: 1,
  },
  {
    id: 'courses',
    role: 'employee',
    target: '[data-tour="home-courses"]',
    title: 'onboarding.tour.courses.title',
    body: 'onboarding.tour.courses.body',
    order: 2,
  },
  {
    id: 'skillmap',
    role: 'employee',
    target: '[data-tour="home-skillmap"]',
    title: 'onboarding.tour.skillmap.title',
    body: 'onboarding.tour.skillmap.body',
    order: 3,
  },
  {
    id: 'start',
    role: 'employee',
    target: '[data-tour="home-start"]',
    title: 'onboarding.tour.start.title',
    body: 'onboarding.tour.start.body',
    order: 4,
  },
]

/**
 * The admin product tour (docs/design/onboarding.md §3.2, Fase 1). Same "encuadre →
 * recorrido → primera victoria" shape as the employee one, but the *aha* is
 * "esto genera formación solo": it ends on the create-course action, the owner's
 * first win.
 *
 * Every step anchors to the admin sidebar — the always-present control panel on the
 * `/admin` home, stable across the org and individual workspace modes. The runner
 * drops any step whose anchor is not visible (e.g. "Empleados" is absent in an
 * individual workspace), so the same list stays correct in both modes without a
 * branch here.
 *
 * The create step is the natural place for a `requires: 'generation'` tag once the
 * Capabilities hook lands (Fase 2) — dropping it when there is no AI key so the tour
 * never ends on a dead action. Left untagged for now: that signal does not exist yet.
 */
export const adminTourSteps: OnboardingStep[] = [
  {
    id: 'admin-welcome',
    role: 'admin',
    target: '[data-tour="admin-home"]',
    title: 'onboarding.tour.admin.welcome.title',
    body: 'onboarding.tour.admin.welcome.body',
    order: 1,
  },
  {
    id: 'admin-content',
    role: 'admin',
    target: '[data-tour="admin-content"]',
    title: 'onboarding.tour.admin.content.title',
    body: 'onboarding.tour.admin.content.body',
    order: 2,
  },
  {
    id: 'admin-team',
    role: 'admin',
    target: '[data-tour="admin-employees"]',
    title: 'onboarding.tour.admin.team.title',
    body: 'onboarding.tour.admin.team.body',
    order: 3,
  },
  {
    id: 'admin-create',
    role: 'admin',
    target: '[data-tour="admin-create-course"]',
    title: 'onboarding.tour.admin.create.title',
    body: 'onboarding.tour.admin.create.body',
    order: 4,
  },
]

/** Every tour step, both roles. The runner picks its slice with `resolveSteps`. */
export const tourSteps: OnboardingStep[] = [...employeeTourSteps, ...adminTourSteps]

/**
 * Steps for a role, capability-filtered and ordered. In Fase 0 `capabilities` is
 * absent and no step declares `requires`, so this is just the ordered role list;
 * the signature is already the §2.3 filter so Fase 1/2 pass real capabilities.
 */
export function resolveSteps(
  steps: OnboardingStep[],
  role: 'employee' | 'admin',
  capabilities?: Partial<Record<NonNullable<OnboardingStep['requires']>, boolean>>,
): OnboardingStep[] {
  return steps
    .filter((s) => s.role === role)
    .filter((s) => !s.requires || Boolean(capabilities?.[s.requires]))
    .sort((a, b) => a.order - b.order)
}
