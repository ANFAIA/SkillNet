import { InlineMarkdown } from './InlineMarkdown'
import { ClickableText } from '../ClickableText'
import { BLOCK_TITLE } from './rhythm'

export interface StepSequenceBlockProps {
  title: string
  steps: string[]
}

/**
 * Procedure, 2-7 steps. An <ol> so screen readers and "step 3 of 5" navigation
 * come for free; the visible numbers are the list marker rendered manually
 * because the counter needs to align with multi-line step text.
 *
 * §8.5: one `ClickableText` for the whole procedure, not one per step — a
 * seven-step list would otherwise be seven tab stops. Context is still per step,
 * because `BLOCK_SELECTOR` stops at the `<li>`.
 */
export function StepSequenceBlock({ title, steps }: StepSequenceBlockProps) {
  const items = Array.isArray(steps) ? steps : []

  return (
    <ClickableText as="div" className="min-w-0">
      {title ? <p className={BLOCK_TITLE}>{title}</p> : null}
      <ol className="space-y-2.5 min-w-0">
        {items.map((step, idx) => (
          <li key={idx} className="flex gap-3 min-w-0">
            <span
              aria-hidden="true"
              // The step number is a list marker, not a word: without this the
              // walk would turn "3" into a clickable term.
              data-no-explain=""
              // `text-xs`, not the `text-[11px]` this used to carry: an off-scale
              // size next to captions that are 12px reads as a rendering accident.
              className="shrink-0 mt-0.5 w-5 h-5 rounded-full border border-border bg-bg-subtle text-xs font-medium text-text-secondary flex items-center justify-center"
            >
              {idx + 1}
            </span>
            <span className="text-sm text-text-secondary leading-relaxed min-w-0">
              <InlineMarkdown>{step}</InlineMarkdown>
            </span>
          </li>
        ))}
      </ol>
    </ClickableText>
  )
}
