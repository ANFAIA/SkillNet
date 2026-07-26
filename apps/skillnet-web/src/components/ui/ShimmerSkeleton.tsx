import { motion, useReducedMotion } from 'framer-motion'
import { shimmer } from '../../lib/motion'

export interface ShimmerSkeletonProps {
  /** Sizing/radius classes for the placeholder, e.g. `h-3.5 w-4/5`. */
  className?: string
}

/**
 * Loading placeholder with a transform-based shimmer sweep.
 *
 * Deliberately a NEW component instead of a change to `ui/Skeleton.tsx` (§9.2):
 * that file uses `animate-pulse` and is re-exported as `SkeletonText` /
 * `SkeletonCard` / `SkeletonRow` across v1 pages, so touching it would be a
 * visible v1 change with the flag off.
 *
 * Under `prefers-reduced-motion` the sweep is dropped entirely — a static muted
 * block is the accessible degradation, not a slower animation.
 */
export function ShimmerSkeleton({ className = '' }: ShimmerSkeletonProps) {
  const reduceMotion = useReducedMotion()

  return (
    <div
      aria-hidden="true"
      data-no-explain=""
      className={`relative overflow-hidden bg-bg-muted rounded ${className}`}
    >
      {!reduceMotion && (
        <motion.div
          className="absolute inset-y-0 -inset-x-full bg-linear-to-r from-transparent via-white/70 to-transparent"
          initial={shimmer.initial}
          animate={shimmer.animate}
          transition={shimmer.transition}
        />
      )}
    </div>
  )
}

/** Text placeholder — staggered line widths so it reads as prose, not as bars. */
export function ShimmerSkeletonText({ lines = 3 }: { lines?: number }) {
  const widths = ['w-full', 'w-11/12', 'w-4/5', 'w-full', 'w-2/3']
  return (
    <div className="space-y-2.5">
      {Array.from({ length: lines }).map((_, i) => (
        <ShimmerSkeleton key={i} className={`h-3.5 ${widths[i % widths.length]}`} />
      ))}
    </div>
  )
}
