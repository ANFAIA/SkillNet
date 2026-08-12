/**
 * Onboarding and learner profile (§11.2).
 *
 * The **questions come from the server** (`OnboardingRead.questions`): the wording
 * lives in exactly one place, and the RGPD art. 13 notice in particular is a field
 * of the response, not client copy (§3.3). The wizard renders what it is given and
 * never invents a question — that is also what guarantees it cannot offer an
 * accommodation the product does not have (there is no TTS in this PR, so there is
 * no "read aloud" option to render, §6.2).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, get, patch, post } from './client'

export type LearningPreset = 'standard' | 'focus' | 'fast'

/**
 * What the learner may declare. `'unknown'` is **not** here on purpose: it is what
 * the server writes when the wizard is skipped, never something the client sends.
 * Sending `'none'` for "did not answer" would declare the learner a novice and
 * force novice scaffolding — the case that hurts the expert (§6.1).
 */
export type ExperienceLevel = 'none' | 'some' | 'experienced'

export type PresentationPreference = 'balanced' | 'visual' | 'textual' | 'interactive'
export type DetailPreference = 'concise' | 'standard' | 'detailed'
export type ImagePreference = 'when_useful' | 'prefer' | 'avoid'

export interface LearningPreferences {
  presentation: PresentationPreference
  detail: DetailPreference
  images: ImagePreference
}

export const DEFAULT_LEARNING_PREFERENCES: LearningPreferences = {
  presentation: 'balanced',
  detail: 'standard',
  images: 'when_useful',
}

export type OnboardingQuestionKind = 'text_suggest' | 'single_choice' | 'multi_choice'

/** The four reading settings of question 5 (`users.accessibility`, §6.2). */
export const ACCESSIBILITY_KEYS = [
  'short_blocks',
  'reduce_motion',
  'high_contrast',
  'extra_time',
] as const

export type AccessibilityKey = (typeof ACCESSIBILITY_KEYS)[number]

export type AccessibilitySettings = Record<AccessibilityKey, boolean>

export const NO_ACCESSIBILITY: AccessibilitySettings = {
  short_blocks: false,
  reduce_motion: false,
  high_contrast: false,
  extra_time: false,
}

export function isAccessibilityKey(value: string): value is AccessibilityKey {
  return (ACCESSIBILITY_KEYS as readonly string[]).includes(value)
}

export interface OnboardingOption {
  value: string
  label: string
  hint?: string
}

export interface OnboardingQuestion {
  id: string
  kind: OnboardingQuestionKind
  prompt: string
  suggestions?: string[]
  options?: OnboardingOption[]
  allow_other?: boolean
  optional?: boolean
}

export interface OnboardingRead {
  version: number
  completed: boolean
  /** RGPD art. 13 notice. Rendered on screen 1 with body weight, never as fine print. */
  notice: string
  questions: OnboardingQuestion[]
}

export interface OnboardingSubmitBody {
  role_title?: string
  sector?: string
  goal?: string
  experience_level?: ExperienceLevel
  preset?: LearningPreset
  learning_preferences?: LearningPreferences
  accessibility?: AccessibilitySettings
}

/** `format_vector` and `tutor_notes` are never exposed to the client (§11.2). */
export interface LearnerProfileRead {
  role_title: string | null
  sector: string | null
  goal: string | null
  experience_level: string
  preset: string
  learning_preferences: LearningPreferences
  nodes_completed: number
  onboarding_completed_at: string | null
  onboarding_skipped: boolean
  calibrating: boolean
}

export const onboardingKey = ['onboarding'] as const
export const learnerProfileKey = ['users', 'me', 'learner-profile'] as const

export function useOnboardingQuestions(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: onboardingKey,
    queryFn: () => get<OnboardingRead>('/onboarding'),
    enabled: options?.enabled ?? true,
    staleTime: Infinity, // the copy does not change mid-session
    retry: false,
  })
}

/**
 * `null` means the server answered **404**, and 404 means "do not redirect" — not
 * "not onboarded" (§6.1, rule 3).
 *
 * With the flag off or in `shadow` every employee route of §11 is a plain 404. If
 * the client read that as "no profile yet ⇒ send them to /onboarding", turning the
 * flag off mid-session would bounce the user towards a route that no longer
 * exists, forever. Mapping it to `null` here — instead of leaving it to each
 * caller's error branch — is what makes that impossible to get wrong.
 */
async function fetchLearnerProfile(): Promise<LearnerProfileRead | null> {
  try {
    return await get<LearnerProfileRead>('/users/me/learner-profile')
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}

export function useLearnerProfile(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: learnerProfileKey,
    queryFn: fetchLearnerProfile,
    enabled: options?.enabled ?? true,
    retry: false,
  })
}

export interface LearnerProfileUpdate {
  role_title?: string | null
  sector?: string | null
  goal?: string | null
  preset?: LearningPreset
  learning_preferences?: LearningPreferences
  accessibility?: AccessibilitySettings
}

export function useUpdateLearnerProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: LearnerProfileUpdate) =>
      patch<LearnerProfileRead>('/users/me/learner-profile', body),
    onSuccess: (profile) => {
      queryClient.setQueryData(learnerProfileKey, profile)
      queryClient.invalidateQueries({ queryKey: learnerProfileKey })
      queryClient.invalidateQueries({ queryKey: ['users', 'me'], exact: true })
      queryClient.removeQueries({
        predicate: (query) => {
          const key = query.queryKey
          return key[0] === 'nodes' && (key[2] === 'render' || key[2] === 'renders')
        },
      })
    },
  })
}

/**
 * `POST /onboarding` — writes `learner_profiles`, `users.learning_profile` and
 * `users.accessibility` in a single transaction (§11.2). That is why the wizard
 * submits everything here in one shot instead of PATCHing field by field.
 */
export function useSubmitOnboarding() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: OnboardingSubmitBody) =>
      post<LearnerProfileRead>('/onboarding', body),
    onSuccess: (profile) => {
      queryClient.setQueryData(learnerProfileKey, profile)
      // `users.learning_profile` and `users.accessibility` changed in the same
      // transaction, so the cached identity is stale. `exact` matters: without it
      // the prefix would also invalidate the profile we just wrote above.
      queryClient.invalidateQueries({ queryKey: ['users', 'me'], exact: true })
    },
  })
}

/**
 * "Lo hago luego" — the server writes `experience_level = 'unknown'` and
 * `onboarding_skipped = true` (§6.1). The client sends **no answers at all**: a
 * skip is the absence of a declaration, and submitting `'none'` here would be the
 * one mistake §6.1 singles out.
 */
export function useSkipOnboarding() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => post<LearnerProfileRead>('/onboarding/skip'),
    onSuccess: (profile) => {
      queryClient.setQueryData(learnerProfileKey, profile)
      queryClient.invalidateQueries({ queryKey: ['users', 'me'], exact: true })
    },
  })
}
