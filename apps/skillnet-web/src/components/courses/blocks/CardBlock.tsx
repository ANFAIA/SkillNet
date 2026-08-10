import type { ReactNode } from 'react'
import { ClickableText } from '../ClickableText'

export interface CardBlockProps {
  title: string
  children?: ReactNode
}

/**
 * Grouping container. The one block that is *outer* chrome around other blocks,
 * so it stays a size larger than what it holds: `p-6` and `gap-4`, against the
 * `p-5` (`INLINE_SURFACE`) of a Callout or a QuizItem sitting inside it.
 *
 * Depth is a hairline outline on the theater's base surface (`bg-bg`), not a
 * shadow — the inline blocks it wraps carry the raised `bg-bg-subtle` tone, so
 * the layering reads on its own. The title is a lesson heading (`text-lesson-title`),
 * divided from the body by the same 1px border as the frame.
 *
 * §8.5 "titulos incluidos": the title is the one piece of text a Card owns and is
 * where the unfamiliar noun usually is, so it is a `ClickableText`. The children
 * clickify themselves — each is another block.
 */
export function CardBlock({ title, children }: CardBlockProps) {
  return (
    <section className="min-w-0 w-full rounded-xl border border-border bg-bg p-6">
      {title ? (
        <h3 className="text-lesson-title text-text mb-5 pb-5 border-b border-border">
          <ClickableText>{title}</ClickableText>
        </h3>
      ) : null}
      <div className="flex flex-col gap-4 min-w-0">{children}</div>
    </section>
  )
}
