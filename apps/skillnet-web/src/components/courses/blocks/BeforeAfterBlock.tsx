import { useIntl } from 'react-intl'
import { BLOCK_TITLE } from './rhythm'
import { ClickableText } from '../ClickableText'
import { InlineMarkdown } from './InlineMarkdown'

export interface BeforeAfterBlockProps {
  title: string
  beforeLabel: string
  beforeContent: string
  afterLabel: string
  afterContent: string
}

/**
 * A two-state contrast shown **side by side, both always visible** (the Curio
 * "Heliocentric vs Geocentric" pattern). It used to be a drag-to-reveal slider —
 * that hid half the content behind an action that taught nothing, so it is gone:
 * a comparison the reader has to uncover is a comparison they cannot make.
 *
 * Two calm panels. The "after" is framed by a full accent border (not a single
 * coloured edge, which reads as template slop) to mark the improved state.
 * Stacks on narrow widths, side by side from `sm` up.
 */

/** A whole-content fenced code block, e.g. a before/after refactor. */
const CODE_FENCE = /^\s*```[\w-]*\n([\s\S]*?)```\s*$/

/** Render one side: code as code (monospace slab), everything else as prose. */
function SideContent({ content, muted }: { content: string; muted: boolean }) {
  const fence = content.match(CODE_FENCE)
  if (fence) {
    return (
      <pre
        data-no-explain=""
        className="min-w-0 overflow-x-auto rounded-lg border border-border bg-bg-muted p-3 font-mono text-[13px] leading-relaxed text-text"
      >
        <code>{fence[1].replace(/\n$/, '')}</code>
      </pre>
    )
  }
  return (
    <ClickableText
      as="p"
      className={`text-lesson-body whitespace-pre-wrap min-w-0 ${muted ? 'text-text-secondary' : 'text-text'}`}
    >
      <InlineMarkdown>{content}</InlineMarkdown>
    </ClickableText>
  )
}

export function BeforeAfterBlock({
  title,
  beforeLabel,
  beforeContent,
  afterLabel,
  afterContent,
}: BeforeAfterBlockProps) {
  const intl = useIntl()
  const before = beforeLabel || intl.formatMessage({ id: 'beforeafter.before' })
  const after = afterLabel || intl.formatMessage({ id: 'beforeafter.after' })

  // A code slab needs the full column width to stay readable — squeezed into a
  // ~245px half it clips and scrolls sideways, unreadable. So when EITHER side is
  // a fenced code block the two panels stack (one column, full width each); short
  // prose comparisons keep the side-by-side two-column layout from `sm` up.
  const hasCode = CODE_FENCE.test(beforeContent) || CODE_FENCE.test(afterContent)

  return (
    <div className="min-w-0">
      {title ? <p className={BLOCK_TITLE}>{title}</p> : null}

      <div className={`grid grid-cols-1 gap-3 ${hasCode ? '' : 'sm:grid-cols-2'}`}>
        {/* Before — neutral frame */}
        <section className="min-w-0 rounded-xl border border-border bg-bg-subtle p-4">
          <p className="text-lesson-caption font-medium tracking-wide text-text-muted mb-2">
            {before}
          </p>
          <SideContent content={beforeContent} muted />
        </section>

        {/* After — full accent frame marks the improved / correct state */}
        <section className="min-w-0 rounded-xl border border-accent bg-bg-subtle p-4">
          <p className="text-lesson-caption font-medium tracking-wide text-accent mb-2">
            {after}
          </p>
          <SideContent content={afterContent} muted={false} />
        </section>
      </div>
    </div>
  )
}
