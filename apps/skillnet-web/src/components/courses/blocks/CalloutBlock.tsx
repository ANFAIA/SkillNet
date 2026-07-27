import { InlineMarkdown } from './InlineMarkdown'
import { ClickableText } from '../ClickableText'
import { BLOCK_EYEBROW, INLINE_SURFACE } from './rhythm'
import type { CalloutTone } from '../kit/schemas'

export interface CalloutBlockProps {
  tone?: CalloutTone
  text: string
}

// Hierarchy through a left rule + a subtle surface, not a pastel block with a
// coloured icon circle (design-system.md anti-patterns). The tones are the existing
// status colours and their `*-subtle` tints — `warn` used to have no tint at all
// (`bg-bg-subtle`), which left the loudest tone as the only silent surface.
const toneClasses: Record<CalloutTone, string> = {
  info: 'border-l-primary bg-primary-subtle',
  warn: 'border-l-warning bg-warning-subtle',
  success: 'border-l-accent bg-accent-subtle',
}

const toneLabels: Record<CalloutTone, string> = {
  info: 'Importante',
  warn: 'Atencion',
  success: 'Correcto',
}

export function CalloutBlock({ tone = 'info', text }: CalloutBlockProps) {
  const resolved = toneClasses[tone] ? tone : 'info'

  return (
    <aside
      // `note` keeps it out of the landmark list while still announcing as an
      // aside; the visible label carries the tone for non-sighted users, which
      // a colour-only cue would not.
      role="note"
      aria-label={toneLabels[resolved]}
      className={`${INLINE_SURFACE} border-l-2 ${toneClasses[resolved]}`}
    >
      {/* The tone label is chrome, not lesson prose: it is deliberately outside
          the ClickableText, so "Atencion" is not a term anyone can explain. */}
      <p className={`${BLOCK_EYEBROW} text-text-secondary`}>{toneLabels[resolved]}</p>
      <ClickableText as="p" className="text-sm text-text leading-relaxed min-w-0">
        <InlineMarkdown>{text}</InlineMarkdown>
      </ClickableText>
    </aside>
  )
}
