import { motion } from 'framer-motion'
import { spring } from '../../lib/motion'

/**
 * Active-nav pill (`--frame-pill-bg`: a light, high-contrast surface on both
 * light and dark rails). Rendered as an absolutely-positioned background inside
 * the *active* NavLink; framer-motion's shared-layout (`layoutId`) slides it
 * between items with spring physics as the active route changes — no manual
 * measurement, so it's robust to StrictMode ref detach/reattach.
 *
 * `inset-0` makes it inherit the NavLink's own box, so it fuses to the right
 * edge of the sidebar (expanded) and becomes an inset chip (collapsed) for free.
 */
export function NavPill({
  layoutId,
  collapsed,
  connected = false,
}: {
  layoutId: string
  collapsed: boolean
  connected?: boolean
}) {
  return (
    <motion.span
      layoutId={layoutId}
      aria-hidden
      className={`absolute inset-0 pointer-events-none ${
        connected
          ? 'connected-nav-pill'
          : `bg-[var(--frame-pill-bg)] ${collapsed ? 'rounded-lg' : 'rounded-l-xl'}`
      }`}
      transition={spring.stiff}
    />
  )
}
