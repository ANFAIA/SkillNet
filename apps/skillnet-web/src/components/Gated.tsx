import type { ReactNode } from 'react'
import { useCapability, type Capabilities } from '../api/setup'

/**
 * Declarative capability gate (docs/design/onboarding.md §2.2). Renders its children
 * only when the required capability is present; otherwise renders nothing — never an
 * error or a dead-end. The rule: an AI element lights up only if its capability is
 * there. Without the key it simply isn't shown (the pre-cooked side stays complete).
 *
 * ```tsx
 * <Gated requires="tutor">
 *   <TutorPromptChip />
 * </Gated>
 * ```
 *
 * Prefer this over scattering `if (capabilities.x)` conditionals. For a boolean in
 * logic (not JSX), use {@link useCapability} directly.
 */
export function Gated({
  requires,
  children,
  fallback = null,
}: {
  requires: keyof Capabilities
  children: ReactNode
  /** Rendered instead when the capability is absent. Defaults to nothing. */
  fallback?: ReactNode
}) {
  const enabled = useCapability(requires)
  return <>{enabled ? children : fallback}</>
}
