import { InlineMarkdown } from './InlineMarkdown'
import { ClickableText } from '../ClickableText'
import type { TextVariant } from '../kit/schemas'

export interface TextContentBlockProps {
  text: string
  variant?: TextVariant
}

// `lead` is the first-child slot of §5.2 rule 7 — the "esto te sirve para X"
// line. It gets weight and the primary text colour; body stays secondary so a
// wall of prose does not compete with it.
const variantClasses: Record<TextVariant, string> = {
  lead: 'text-base text-text leading-relaxed',
  body: 'text-sm text-text-secondary leading-relaxed',
  caption: 'text-xs text-text-muted leading-relaxed',
}

/**
 * §8.5: the paragraph *is* the `ClickableText` group, so a clicked word has
 * exactly one enclosing `BLOCK_SELECTOR` element and `ClickableSurface` sends
 * the whole paragraph as context — no wrapper duplicating the same text.
 */
export function TextContentBlock({ text, variant = 'body' }: TextContentBlockProps) {
  return (
    <ClickableText as="p" className={`min-w-0 ${variantClasses[variant] ?? variantClasses.body}`}>
      <InlineMarkdown>{text}</InlineMarkdown>
    </ClickableText>
  )
}
