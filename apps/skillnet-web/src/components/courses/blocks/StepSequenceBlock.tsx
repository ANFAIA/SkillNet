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
      <ol className="min-w-0">
        {items.map((step, idx) => {
          const isLast = idx === items.length - 1
          return (
            <li
              key={idx}
              className="flex gap-4 min-w-0"
              style={{
                opacity: 0,
                animation: `step-fade-in 0.3s ease forwards`,
                animationDelay: `${idx * 60}ms`,
              }}
            >
              {/* Timeline column: circle + connecting line */}
              <div className="flex flex-col items-center shrink-0">
                <span
                  aria-hidden="true"
                  data-no-explain=""
                  className="w-7 h-7 rounded-full bg-primary text-white text-xs font-semibold flex items-center justify-center shadow-sm"
                >
                  {idx + 1}
                </span>
                {/* Vertical connector line between steps */}
                {!isLast && (
                  <div
                    aria-hidden="true"
                    className="w-0.5 flex-1 bg-border-strong mt-1"
                  />
                )}
              </div>
              {/* Step content */}
              <div className={`text-sm text-text leading-relaxed min-w-0 ${isLast ? '' : 'pb-5'}`}>
                <InlineMarkdown>{step}</InlineMarkdown>
              </div>
            </li>
          )
        })}
      </ol>
    </ClickableText>
  )
}
