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
