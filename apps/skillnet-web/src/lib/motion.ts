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
  /** Gooey — elastic overshoot for the chat input button morph */
  gooey: [0.32, 0.72, 0, 1] as const,
} as const

// ── Durations (seconds) ──────────────────────────────────────
export const duration = {
  /** Instant feedback — color, background, icon state */
  instant: 0.125,
  /** Fast — tooltips, dropdowns, focus rings */
  fast: 0.2,
  /** Normal — fade content transitions */
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
  /** Page/route transitions — opacity fade, no scale (keeps nav snappy) */
  page: { duration: duration.normal, ease: ease.base },
  /**
   * Route *exit*. Deliberately shorter and accelerating: entering a screen is a
   * deliberate act, leaving one is not (the enter/exit asymmetry of the iOS
   * navigation controller, motion-system.md §4). Symmetric 300/300 spent 600 ms of
   * dead time on every click in the nav.
   */
  pageOut: { duration: duration.fast, ease: ease.snapOut },
  /** Content swap within a page (lesson switch, tab change) */
  content: { duration: duration.normal, ease: ease.base },
  /** Layout morph (layoutId transitions) */
  layout: { duration: duration.slow, ease: ease.base },
  /**
   * A container settling to a new size around content that was swapped or that
   * just arrived (wizard step height, the reserved node content area). Structural,
   * so `medium` rather than `normal` — but not `slow`: nobody is waiting on a
   * modal here, the content is already readable while the box catches up.
   */
  resize: { duration: duration.medium, ease: ease.base },
  /** Panel push-in */
  pushIn: { duration: 0.4, ease: ease.snapIn },
  /** Panel push-out */
  pushOut: { duration: duration.fast, ease: ease.snapOut },
  /** Micro-interaction (hover, tap) */
  micro: { type: 'spring' as const, stiffness: 500, damping: 30 },
  /**
   * A tooltip or popover appearing next to the control that summoned it. `fast`,
   * because it is an answer to something the pointer is already doing — anything
   * slower reads as lag rather than as motion.
   */
  tooltip: { duration: duration.fast, ease: ease.base },
} as const

// ── Reusable animation states ────────────────────────────────

/**
 * Page transition: opacity fade (no scale, no blur). Keeps things snappy and
 * does not compete with the sliding nav pill.
 *
 * ⚠️ `exit` is for an `AnimatePresence` whose children are **stable** — content you
 * hand it directly, as MotionDemo does. Do **not** spread the whole preset into an
 * `AnimatePresence mode="wait"` wrapped around a react-router `<Outlet />`.
 *
 * `Outlet` is not frozen: under `mode="wait"` the outgoing element stays mounted to
 * play its exit while React re-renders its subtree against the *new* location, so the
 * incoming page mounts inside the node that is exiting. If that page registers a
 * `layoutId` from in there, framer never calls `safeToRemove` for the exiting key, the
 * incoming child is never swapped in, and the whole main area is left blank at
 * `opacity: 0` until the next navigation. That was a real, shipped bug on
 * /empleado/cursos; both route layouts are now enter-only for this reason and pass
 * `initial`/`animate` explicitly rather than spreading. See `AppLayout.tsx`.
 */
export const pageTransition = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: transition.page },
  exit: { opacity: 0, transition: transition.pageOut },
  // Kept as the element-level default for anything the two variants above do not
  // name; the per-variant transitions are what make the exit the fast half.
  transition: transition.page,
} as const

/** Content swap: opacity + slight Y offset */
export const contentSwap = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
  transition: transition.content,
} as const

/** Stagger container — apply to parent, children use staggerItem */
export const staggerContainer = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.06 } },
} as const

/** Stagger item — opacity + slide up */
export const staggerItem = {
  hidden: { opacity: 0, y: 12 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: duration.normal, ease: ease.base },
  },
} as const

/** Item exit — opacity + slide left */
export const itemExit = {
  opacity: 0,
  x: -64,
  transition: { duration: duration.normal, ease: ease.snapOut },
} as const

/** Slide variants for directional navigation (wizard steps, push nav) */
export function slideVariants(distance: number | string = 80) {
  return {
    enter: (dir: 1 | -1) => ({
      x: dir > 0 ? distance : typeof distance === 'number' ? -distance : `-${distance}`,
      opacity: 0,
    }),
    center: { x: 0, opacity: 1 },
    exit: (dir: 1 | -1) => ({
      x: dir > 0 ? (typeof distance === 'number' ? -distance : `-${distance}`) : distance,
      opacity: 0,
    }),
  }
}

/**
 * Wizard step slide, with the enter/exit asymmetry the plain `slideVariants` does
 * not carry.
 *
 * A 5-screen wizard with a symmetric 300 ms slide and `AnimatePresence mode="wait"`
 * spends 600 ms per step doing nothing — 3 s of the ≤90 s budget §6.1 sets for
 * onboarding, and the reason the wizard *reads* long even though it is short. The
 * outgoing step leaves in `fast` and accelerating; the incoming one still lands on
 * the signature curve, so nothing feels rushed, only the gap disappears.
 */
export function stepSlideVariants(distance: number | string = 64) {
  const base = slideVariants(distance)
  return {
    enter: base.enter,
    center: { ...base.center, transition: transition.content },
    exit: (dir: 1 | -1) => ({ ...base.exit(dir), transition: transition.pushOut }),
  }
}

/**
 * Generated blocks entering the node view one after another (§9.2).
 *
 * Implemented in CSS (`.block-arrival` in `index.css`) rather than as framer
 * variants, because the children being staggered are produced by OpenUI's runtime:
 * we never hold a mappable child array, only the container. These are the numbers
 * that file mirrors — the same 60 ms cadence and the same opacity + rise as
 * `staggerItem`, so a generated lesson and a hand-written list arrive alike.
 */
export const blockArrival = {
  /** Seconds between one block and the next. Matches `staggerContainer`. */
  stagger: 0.06,
  /** How long a single block takes to resolve. */
  duration: duration.normal,
  /** Blocks past this index all share the last delay — §5.2 rule 4 caps root fan-out at 5. */
  maxStaggered: 8,
} as const

/** Sidebar/overlay backdrop */
export const backdrop = {
  initial: { opacity: 0 },
  animate: { opacity: 1 },
  exit: { opacity: 0 },
  transition: { duration: duration.fast },
} as const

/**
 * Loading shimmer — a highlight band swept across a placeholder.
 *
 * `transform` only: `animate-pulse` is banned (motion-system.md:437,636) because
 * an infinite opacity loop reads as generic and repaints the whole element.
 * Sweeping a translated band keeps the work on the compositor.
 * Consumed by `ui/ShimmerSkeleton.tsx`; skip it under `prefers-reduced-motion`.
 */
export const shimmer = {
  initial: { x: '-100%' },
  animate: { x: '100%' },
  transition: {
    duration: 1.4,
    ease: ease.base,
    repeat: Infinity,
    repeatDelay: 0.25,
  },
} as const

/** Sidebar slide-in from left */
export const sidebarSlide = {
  initial: { x: '-100%' },
  animate: { x: 0 },
  exit: { x: '-100%' },
  transition: spring.default,
} as const
