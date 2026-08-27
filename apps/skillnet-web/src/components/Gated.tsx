import { Children, type ReactElement, type ReactNode } from 'react'
import { isAvailable, useCapability, type CapabilityName } from '../api/setup'
import { CapabilityExplain } from './CapabilityExplain'

/**
 * What `<Gated>` does when the capability is not there.
 *
 * * `hide` (default) — renders nothing, or the `fallback`. Today's behaviour, and
 *   still the right one for an AI extra that simply is not part of this deployment:
 *   the pre-cooked side stays complete and nobody is shown a dead end.
 * * `explain` — renders the control, visible but inert, with the reason attached.
 *   For an option a learner would look for and not find: the choice is real, it is
 *   just not available *here*, and hiding it only moves the confusion.
 */
export type GateMode = 'hide' | 'explain'

/**
 * Declarative capability gate (docs/design/onboarding.md §2.2). Renders its children
 * only when the required capability is present; otherwise, per {@link GateMode},
 * either nothing or a visibly-disabled control that says why. Never an error, and
 * never a control that fires a job doomed to die on the backend.
 *
 * ```tsx
 * <Gated requires="tutor">
 *   <TutorPromptChip />
 * </Gated>
 *
 * <Gated requires="images" mode="explain">
 *   <button type="button" onClick={pickInfographic}>Infografía</button>
 * </Gated>
 * ```
 *
 * The two modes use **different bars**, and that is on purpose:
 *
 * * `hide` asks "does this capability exist at all?" — a `degraded` capability does
 *   (the offline voice still speaks), so its UI stays. Only `blocked` removes it.
 * * `explain` asks "can this click succeed?" — anything short of `ready` (over quota,
 *   provider down, no key) can fail, and the right answer to a maybe is to say so
 *   rather than to spend a generation finding out.
 *
 * Prefer this over scattering `if (capabilities.x)` conditionals. For a status in
 * logic (not JSX), use {@link useCapability} directly.
 */
export function Gated({
  requires,
  mode = 'hide',
  children,
  fallback = null,
}: {
  requires: CapabilityName
  /** Defaults to `hide` so every existing call site keeps its behaviour. */
  mode?: GateMode
  children: ReactNode
  /** Rendered instead when the capability is absent, in `hide` mode. Defaults to nothing. */
  fallback?: ReactNode
}) {
  const capability = useCapability(requires)

  if (mode === 'explain') {
    // Only a BLOCKED capability is explained away. `degraded` is the keyless TTS state,
    // where the offline voice still produces audio — saying "no está disponible" over a
    // control that works would be the lie this copy exists to avoid. A caller that wants
    // to warn about a reduced result says so next to the action, not on it.
    if (isAvailable(capability)) return <>{children}</>
    // `explain` needs one element to clone props onto — a fragment or a list has no
    // control to disable and nothing to describe.
    return (
      <CapabilityExplain requires={requires}>
        {Children.only(children) as ReactElement}
      </CapabilityExplain>
    )
  }

  return <>{isAvailable(capability) ? children : fallback}</>
}
