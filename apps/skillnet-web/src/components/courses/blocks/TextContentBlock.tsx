import { InlineMarkdown } from './InlineMarkdown'
import { ClickableText } from '../ClickableText'
import type { TextVariant } from '../kit/schemas'

export interface TextContentBlockProps {
  text: string
  variant?: TextVariant
}

// The lesson type scale (see `--text-lesson-*` in index.css): a course screen
// is read like a page, not like UI chrome, so these are larger and airier than
// the app's text-sm/text-xs. Hierarchy is carried by size and weight, never by
// dimming the body — a single paragraph on its own screen must read at full
// contrast.
//
// - `lead`: the "esto te sirve para X" hook (§5.2 rule 7). Larger, medium weight.
// - `body`: the paragraph. Full colour, generous line-height.
// - `caption`: a muted aside / pie de figura.
const variantClasses: Record<TextVariant, string> = {
  lead: 'text-lesson-lead font-medium text-text',
  body: 'text-lesson-body text-text',
  caption: 'text-lesson-caption text-text-muted',
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
