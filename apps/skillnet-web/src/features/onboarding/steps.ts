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
 * "esto genera formación solo": it walks the owner THROUGH the real onboarding
 * screens and ends on the create-course action, the owner's first win.
 *
 * Unlike the employee tour (one page, many anchors), each admin step sits on its own
 * real screen and declares its `route`. The runner drives joyride in controlled mode:
 * it navigates to a step's route as the step becomes active and only shows the box
 * once the router has landed there. The flow is:
 *
 *   1. /admin           — welcome (sidebar Inicio)
 *   2. /admin/contenido — "here's your example course, open it" (the "Ver ejemplo" btn)
 *   3. /admin/demo      — "switch the learner and watch it adapt" (the Ana/Bruno toggle)
 *   4. /admin/demo      — "when you're ready, create your own" (the create CTA)
 *
 * The create step carries `requires: 'generation'` (Fase 2): the runner passes live
 * capabilities into `resolveSteps`, so with no AI key the step is dropped and the tour
 * never ends on a dead action.
 */
export const adminTourSteps: OnboardingStep[] = [
  {
    id: 'admin-welcome',
    role: 'admin',
    route: '/admin',
    target: '[data-tour="admin-home"]',
    title: 'onboarding.tour.admin.welcome.title',
    body: 'onboarding.tour.admin.welcome.body',
    order: 1,
  },
  {
    id: 'admin-content',
    role: 'admin',
    route: '/admin/contenido',
    target: '[data-tour="content-demo-open"]',
    title: 'onboarding.tour.admin.content.title',
    body: 'onboarding.tour.admin.content.body',
    order: 2,
  },
  {
    id: 'admin-preview',
    role: 'admin',
    route: '/admin/demo',
    target: '[data-tour="demo-preview-toggle"]',
    title: 'onboarding.tour.admin.preview.title',
    body: 'onboarding.tour.admin.preview.body',
    order: 3,
  },
  {
    id: 'admin-create',
    role: 'admin',
    route: '/admin/demo',
    target: '[data-tour="demo-create-cta"]',
    title: 'onboarding.tour.admin.create.title',
    body: 'onboarding.tour.admin.create.body',
    // Course creation needs a usable LLM. Without it the tour must not end on a dead
    // action, so the step is dropped when `generation` is absent (§2.3).
    requires: 'generation',
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
