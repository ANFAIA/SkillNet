import type { OnboardingState } from './types'

/**
 * MVP persistence for the tour (docs/design/onboarding.md §2.4): a single
 * `localStorage` blob `{ completed, dismissedAt, lastStepId }`. A later phase moves
 * this to a per-user backend field for cross-device; keeping every read/write behind
 * these helpers is what makes that swap a one-file change.
 */
const STORAGE_KEY = 'skillnet-onboarding-tour'

const EMPTY: OnboardingState = { completed: false }

export function readOnboardingState(): OnboardingState {
  if (typeof window === 'undefined') return { ...EMPTY }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...EMPTY }
    const parsed = JSON.parse(raw) as Partial<OnboardingState>
    return {
      completed: Boolean(parsed.completed),
      dismissedAt: parsed.dismissedAt,
      lastStepId: parsed.lastStepId,
    }
  } catch {
    // Corrupt / unavailable storage must never break the app — the tour just
    // behaves as "not seen yet".
    return { ...EMPTY }
  }
}

export function writeOnboardingState(patch: Partial<OnboardingState>): OnboardingState {
  const next: OnboardingState = { ...readOnboardingState(), ...patch }
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      /* ignore quota / disabled storage */
    }
  }
  return next
}

/** Whether the tour should auto-run for a first-time employee. */
export function shouldAutoRun(state: OnboardingState = readOnboardingState()): boolean {
  return !state.completed && !state.dismissedAt
}

export const ONBOARDING_STORAGE_KEY = STORAGE_KEY
