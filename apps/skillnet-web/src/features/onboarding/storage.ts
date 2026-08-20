import type { OnboardingState } from './types'

/**
 * MVP persistence for the tour (docs/design/onboarding.md §2.4): a `localStorage`
 * blob `{ completed, dismissedAt, lastStepId }`, kept **per role** so completing the
 * employee tour never suppresses the admin one (and vice-versa). A later phase moves
 * this to a per-user backend field for cross-device; keeping every read/write behind
 * these helpers is what makes that swap a one-file change.
 */
type TourRole = 'employee' | 'admin'

const STORAGE_KEY_BASE = 'skillnet-onboarding-tour'

/**
 * The employee key stays the bare base (no suffix) so state written before the tour
 * became role-aware still counts; other roles get a suffix.
 */
function storageKey(role: TourRole): string {
  return role === 'employee' ? STORAGE_KEY_BASE : `${STORAGE_KEY_BASE}-${role}`
}

const EMPTY: OnboardingState = { completed: false }

export function readOnboardingState(role: TourRole = 'employee'): OnboardingState {
  if (typeof window === 'undefined') return { ...EMPTY }
  try {
    const raw = window.localStorage.getItem(storageKey(role))
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

export function writeOnboardingState(
  patch: Partial<OnboardingState>,
  role: TourRole = 'employee',
): OnboardingState {
  const next: OnboardingState = { ...readOnboardingState(role), ...patch }
  if (typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(storageKey(role), JSON.stringify(next))
    } catch {
      /* ignore quota / disabled storage */
    }
  }
  return next
}

/** Whether the tour should auto-run for a first-time user of this role. */
export function shouldAutoRun(role: TourRole = 'employee'): boolean {
  const state = readOnboardingState(role)
  return !state.completed && !state.dismissedAt
}

/** The employee storage key, exposed for tests and the backward-compatible default. */
export const ONBOARDING_STORAGE_KEY = STORAGE_KEY_BASE
