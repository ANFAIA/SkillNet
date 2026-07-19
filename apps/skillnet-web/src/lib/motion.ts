/**
 * Motion System — SkillNet
 *
 * Centralized animation presets. Import from here, never hardcode values inline.
 * Docs: /docs/design/motion-system.md
 */

// ── Easing curves ────────────────────────────────────────────
export const ease = {
  /** Signature curve — smooth decelerate, clean landing */
  base: [0.38, 0.49, 0, 1] as const,
  /** Subtle bounce — interactive hover/scale */
  bounce: [0.38, 0.49, 0, 1.16] as const,
  /** Medium bounce — border-radius morphs */
  bounceMid: [0.38, 0.49, 0, 1.5] as const,
  /** Strong bounce — padding expansion, playful effects */
  bounceHard: [0.38, 0.49, 0, 2] as const,
  /** Snappy — panels pushing in */
  snapIn: [0.1, 0.8, 0, 1] as const,
  /** Quick exit — panels pushing out */
  snapOut: [0.1, 0, 0.7, 1] as const,
  /** Shape morph — border-radius on modals */
  morph: [0.56, 0.27, 0, 1] as const,
} as const

// ── Durations (seconds) ──────────────────────────────────────
export const duration = {
  /** Instant feedback — color, background, icon state */
  instant: 0.125,
  /** Fast — tooltips, dropdowns, focus rings */
  fast: 0.2,
  /** Normal — blur/fade content transitions */
  normal: 0.3,
  /** Medium — page transitions, list stagger */
  medium: 0.5,
  /** Slow — modal morph, shared element transitions */
  slow: 0.7,
  /** Morph slow — fullscreen modal border-radius on mobile */
  morphSlow: 1.0,
} as const

// ── Springs ──────────────────────────────────────────────────
export const spring = {
  /** Default — responsive, fast settling */
  default: { type: 'spring' as const, stiffness: 400, damping: 30 },
  /** Bouncy — playful interactive elements */
  bouncy: { type: 'spring' as const, stiffness: 500, damping: 25 },
  /** Stiff — snapping, precise positioning (nav pill) */
  stiff: { type: 'spring' as const, stiffness: 500, damping: 35, mass: 0.5 },
  /** Gentle — large layout shifts */
  gentle: { type: 'spring' as const, stiffness: 200, damping: 25 },
} as const

// ── Reusable transition presets ──────────────────────────────
export const transition = {
  /** Page/route transitions — quick blur-in, no scale (keeps nav snappy) */
  page: { duration: duration.normal, ease: ease.base },
  /** Content swap within a page (lesson switch, tab change) */
  content: { duration: duration.normal, ease: ease.base },
  /** Layout morph (layoutId transitions) */
  layout: { duration: duration.slow, ease: ease.base },
  /** Panel push-in */
  pushIn: { duration: 0.4, ease: ease.snapIn },
  /** Panel push-out */
  pushOut: { duration: duration.fast, ease: ease.snapOut },
  /** Micro-interaction (hover, tap) */
  micro: { type: 'spring' as const, stiffness: 500, damping: 30 },
} as const

// ── Reusable animation states ────────────────────────────────

/**
 * Page transition: quick blur-in (no scale). The scale read as "too much" on
 * every route change; blur alone keeps the iOS depth-of-field feel while staying
 * snappy and not competing with the sliding nav pill.
 */
export const pageTransition = {
  initial: { opacity: 0, filter: 'blur(6px)' },
  animate: { opacity: 1, filter: 'blur(0px)' },
  exit: { opacity: 0, filter: 'blur(6px)' },
  transition: transition.page,
} as const

/** Content swap: blur + slight Y offset */
export const contentSwap = {
  initial: { opacity: 0, filter: 'blur(6px)', y: 8 },
  animate: { opacity: 1, filter: 'blur(0px)', y: 0 },
  exit: { opacity: 0, filter: 'blur(6px)', y: -8 },
  transition: transition.content,
} as const

/** Stagger container — apply to parent, children use staggerItem */
export const staggerContainer = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.06 } },
} as const

/** Stagger item — blur + slide up */
export const staggerItem = {
  hidden: { opacity: 0, y: 12, filter: 'blur(6px)' },
  visible: {
    opacity: 1,
    y: 0,
    filter: 'blur(0px)',
    transition: { duration: duration.normal, ease: ease.base },
  },
} as const

/** Item exit — blur + slide left */
export const itemExit = {
  opacity: 0,
  filter: 'blur(16px)',
  x: -64,
  transition: { duration: duration.normal, ease: ease.snapOut },
} as const

/** Slide variants for directional navigation (wizard steps, push nav) */
export function slideVariants(distance: number | string = 80) {
  return {
    enter: (dir: 1 | -1) => ({
      x: dir > 0 ? distance : typeof distance === 'number' ? -distance : `-${distance}`,
      opacity: 0,
      filter: 'blur(6px)',
    }),
    center: { x: 0, opacity: 1, filter: 'blur(0px)' },
    exit: (dir: 1 | -1) => ({
      x: dir > 0 ? (typeof distance === 'number' ? -distance : `-${distance}`) : distance,
      opacity: 0,
      filter: 'blur(6px)',
    }),
  }
}

/** Sidebar/overlay backdrop */
export const backdrop = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: duration.fast },
} as const

/** Sidebar slide-in from left */
export const sidebarSlide = {
  initial: { x: '-100%' },
  animate: { x: 0 },
  exit: { x: '-100%' },
  transition: spring.default,
} as const
