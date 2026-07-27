import { createContext, useContext } from 'react'
import { useReducedMotion as useSystemReducedMotion } from 'framer-motion'

/**
 * "Should this screen move?", answered from **both** places the learner can say no.
 *
 * `framer-motion`'s own `useReducedMotion()` reads `prefers-reduced-motion`, which is
 * an OS setting. That is only half the question here, because question 5 of the
 * onboarding wizard (§6.2) asks the learner directly — `reduce_motion`, labelled
 * "Menos animaciones" — and stores the answer in `users.accessibility`. Until this
 * hook existed the wizard collected that answer and **nothing in the frontend read
 * it**: someone who ticked the box on a shared work laptop, where they cannot change
 * an OS setting, got the full motion anyway. Asking a question and ignoring it is
 * worse than not asking.
 *
 * So: OS preference OR declared preference. Never the other direction — a learner who
 * declared nothing still gets their OS setting honoured, and neither source can turn
 * motion back *on* for someone the other one silenced.
 *
 * The declared half arrives by context (`ProtectedRoute` provides it, which is where
 * `/auth/me` has already resolved). Outside that tree — Storybook, unit tests, the
 * login screen — the context default is `false` and the hook degrades to exactly what
 * `framer-motion` alone did. Reading it from `useMe()` in every leaf component would
 * instead fire an auth probe from a `ShimmerSkeleton` in a story.
 */
export const declaredReducedMotionContext = createContext(false)

export function useReducedMotion(): boolean {
  const system = useSystemReducedMotion()
  const declared = useContext(declaredReducedMotionContext)
  return system === true || declared
}
