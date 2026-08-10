import { useIntl } from 'react-intl'
import { InlineMarkdown } from './InlineMarkdown'
import { ClickableText } from '../ClickableText'
import { BLOCK_EYEBROW, INLINE_SURFACE } from './rhythm'
import type { CalloutTone } from '../kit/schemas'

export interface CalloutBlockProps {
  tone?: CalloutTone
  text: string
}

// One quiet neutral surface for every tone; the tone speaks through the FULL
// border in its colour plus the coloured eyebrow icon+label. A colour on one
// edge only reads as a template accent — the whole outline carries it instead.
// No pastel fills, no rings — the aside stays calm, just framed in its colour.
const toneClasses: Record<CalloutTone, string> = {
  info: 'border-primary',
  warn: 'border-warning',
  success: 'border-accent',
}

const TONE_LABEL_KEYS: Record<CalloutTone, string> = {
  info: 'callout.info',
  warn: 'callout.warn',
  success: 'callout.success',
}

/** Inline SVG icons per tone — lightweight, no dependency needed. */
function ToneIcon({ tone }: { tone: CalloutTone }) {
  const cls = 'shrink-0 w-4 h-4'
  switch (tone) {
    case 'info':
      return (
        <svg className={cls} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path
            fillRule="evenodd"
            d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.25a.25.25 0 01.25.25v1.75a.75.75 0 001.5 0v-2a1.75 1.75 0 00-1.75-1.75H9z"
            clipRule="evenodd"
          />
        </svg>
      )
    case 'warn':
      return (
        <svg className={cls} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path
            fillRule="evenodd"
            d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.168 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z"
            clipRule="evenodd"
          />
        </svg>
      )
    case 'success':
      return (
        <svg className={cls} viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z"
            clipRule="evenodd"
          />
        </svg>
      )
  }
}

/** Text colour for the tone icon and label so they match the left border. */
const toneLabelColor: Record<CalloutTone, string> = {
  info: 'text-primary',
  warn: 'text-warning',
  success: 'text-accent',
}

export function CalloutBlock({ tone = 'info', text }: CalloutBlockProps) {
  const intl = useIntl()
  const resolved = toneClasses[tone] ? tone : 'info'
  const toneLabel = intl.formatMessage({ id: TONE_LABEL_KEYS[resolved] })

  return (
    <aside
      // `note` keeps it out of the landmark list while still announcing as an
      // aside; the visible label carries the tone for non-sighted users, which
      // a colour-only cue would not.
      role="note"
      aria-label={toneLabel}
      className={`${INLINE_SURFACE} bg-bg-subtle ${toneClasses[resolved]}`}
    >
      {/* The tone label is chrome, not lesson prose: it is deliberately outside
          the ClickableText, so "Atencion" is not a term anyone can explain. */}
      <div className={`flex items-center gap-1.5 ${BLOCK_EYEBROW} ${toneLabelColor[resolved]}`}>
        <ToneIcon tone={resolved} />
        <span className="font-semibold tracking-wide uppercase">{toneLabel}</span>
      </div>
      <ClickableText as="p" className={`text-lesson-body text-text min-w-0 ${resolved === 'warn' ? 'font-medium' : ''}`}>
        <InlineMarkdown>{text}</InlineMarkdown>
      </ClickableText>
    </aside>
  )
}
