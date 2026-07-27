import type { ReactNode } from 'react'
import { blockArrivalContext, useBlockArrival } from './blockArrival'
import { useReducedMotion } from '../../../hooks/useReducedMotion'
import type { StackGap } from '../kit/schemas'

export interface StackBlockProps {
  gap?: StackGap
  children?: ReactNode
}

const gapClasses: Record<StackGap, string> = {
  sm: 'gap-2',
  md: 'gap-4',
  lg: 'gap-6',
}

/**
 * Vertical container. Children are already-resolved React nodes: the renderer
 * owns id resolution so the block stays presentational and story-friendly.
 *
 * It is also the only place that can stage the arrival of a freshly generated
 * lesson, because it is the root of every program (§5.2 rule 1, `library.root`).
 * When `blockArrivalContext` says the render just replaced a skeleton, the container
 * takes `.block-arrival` and its direct children resolve 60 ms apart. The provider is
 * then flipped to `false` so a nested Stack does not re-stagger blocks its parent is
 * already staggering — one cadence per lesson, not one per level of nesting.
 */
export function StackBlock({ gap = 'md', children }: StackBlockProps) {
  const arriving = useBlockArrival()
  const reduceMotion = useReducedMotion()
  // The CSS already drops the animation under `prefers-reduced-motion`; this also
  // drops it for the learner who declared it in the wizard, where no media query
  // applies.
  const arrival = arriving && !reduceMotion ? ' block-arrival' : ''

  return (
    <blockArrivalContext.Provider value={false}>
      <div className={`flex flex-col min-w-0 ${gapClasses[gap] ?? gapClasses.md}${arrival}`}>
        {children}
      </div>
    </blockArrivalContext.Provider>
  )
}
