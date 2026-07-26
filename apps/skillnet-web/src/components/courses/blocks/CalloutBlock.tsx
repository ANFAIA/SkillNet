import { InlineMarkdown } from './InlineMarkdown'
import { ClickableText } from '../ClickableText'
import type { CalloutTone } from '../kit/schemas'

export interface CalloutBlockProps {
  tone?: CalloutTone
  text: string
}

// Hierarchy through a left rule + a subtle surface, not a pastel block with a
// coloured icon circle (design-system.md anti-patterns). The tone tokens are the
// existing status colours; no new colour is introduced.
const toneClasses: Record<CalloutTone, string> = {
  info: 'border-l-primary bg-primary-subtle',
  warn: 'border-l-warning bg-bg-subtle',
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
      className={`border border-border border-l-2 rounded-lg px-4 py-3 min-w-0 ${toneClasses[resolved]}`}
    >
      {/* The tone label is chrome, not lesson prose: it is deliberately outside
          the ClickableText, so "Atencion" is not a term anyone can explain. */}
      <p className="text-xs font-medium text-text-secondary mb-1">{toneLabels[resolved]}</p>
      <ClickableText as="p" className="text-sm text-text leading-relaxed min-w-0">
        <InlineMarkdown>{text}</InlineMarkdown>
      </ClickableText>
    </aside>
  )
}
