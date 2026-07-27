import type { ReactNode } from 'react'
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
 */
export function StackBlock({ gap = 'md', children }: StackBlockProps) {
  return <div className={`flex flex-col min-w-0 ${gapClasses[gap] ?? gapClasses.md}`}>{children}</div>
}
