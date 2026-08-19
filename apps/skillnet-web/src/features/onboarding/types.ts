/**
 * A single guided-tour step, declared as DATA (docs/design/onboarding.md §2.3).
 * joyride only consumes this list; adding / removing / reordering a step is a data
 * edit, never a code branch.
 *
 * `title` / `body` are i18n message ids (resolved at runtime by the runner), so the
 * copy lives in `src/i18n/*` like everything else and stays translatable.
 */
export interface OnboardingStep {
  id: string
  role: 'employee' | 'admin'
  /** CSS selector for the element to spotlight — a stable `[data-tour="…"]`. */
  target: string
  /** i18n id for the step title. */
  title: string
  /** i18n id for the step body (one short sentence). */
  body: string
  order: number
  /**
   * Capability this step needs. Omitted in Fase 0 (no AI-gated steps yet); kept
   * optional so Fase 1/2 can drop a step when the capability is absent
   * (`steps.filter(s => !s.requires || capabilities[s.requires])`).
   */
  requires?: 'ai' | 'generation' | 'tutor' | 'tts' | 'images'
}

/**
 * Per-user onboarding state (docs/design/onboarding.md §2.4). MVP persistence is
 * `localStorage`; a later phase moves it to a per-user field for cross-device.
 */
export interface OnboardingState {
  completed: boolean
  dismissedAt?: string
  lastStepId?: string
}
