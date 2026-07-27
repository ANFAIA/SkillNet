import { createContext, useContext } from 'react'

/**
 * "Did this program just land, or was it already here?"
 *
 * The difference is the whole point. A render the learner waited for should arrive —
 * its blocks resolving one after the other into the space the skeleton was holding.
 * The *same* render served again tomorrow from `active_render_id` must not: it is
 * pinned content the learner has already read, and animating it on load is the
 * anti-pattern motion-system.md names outright ("animar en page load").
 *
 * Only `NodeView` can tell the two apart — it is the component that watched the
 * skeleton — so the answer travels down as context rather than being guessed from a
 * mount. `StackBlock` consumes it and turns it into one class; the stagger itself is
 * `.block-arrival` in `index.css`.
 *
 * `false` everywhere else by default: Storybook, the admin preview and every test
 * render a static program, which is exactly the case that must not animate.
 */
export const blockArrivalContext = createContext(false)

export function useBlockArrival(): boolean {
  return useContext(blockArrivalContext)
}
