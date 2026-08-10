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
      <ol className="flex flex-col gap-4 min-w-0">
        {items.map((step, idx) => (
          <li
            key={idx}
            className="flex gap-4 min-w-0"
            style={{
              opacity: 0,
              animation: `step-fade-in 0.3s ease forwards`,
              animationDelay: `${idx * 60}ms`,
            }}
          >
            {/* Quiet numbered badge: a hairline outline, not a filled chip —
                depth from the border, never a shadow. */}
            <span
              aria-hidden="true"
              data-no-explain=""
              className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border text-xs font-semibold tabular-nums text-text-muted"
            >
              {idx + 1}
            </span>
            {/* Step content — full-contrast lesson body, not dimmed prose. */}
            <div className="text-lesson-body text-text min-w-0">
              <InlineMarkdown>{step}</InlineMarkdown>
            </div>
          </li>
        ))}
      </ol>
    </ClickableText>
  )
}
