import { BLOCK_EYEBROW } from './rhythm'

export interface CodeBlockBlockProps {
  language: string
  code: string
}

/**
 * Code sample. No syntax highlighting: that needs a new dependency and this is a
 * compliance-training product, not an IDE.
 *
 * `data-no-explain` is load-bearing — §8.5 excludes code from click-to-explain,
 * and `ClickableSurface` (B7) hit-tests with `closest('[data-no-explain]')`.
 */
export function CodeBlockBlock({ language, code }: CodeBlockBlockProps) {
  return (
    <div data-no-explain="" className="min-w-0">
      {language ? (
        <p className={`${BLOCK_EYEBROW} font-mono text-text-muted`}>{language}</p>
      ) : null}
      {/* `INLINE_SURFACE` is not spread here: the slab needs `bg-bg-muted` and an
          `overflow-x-auto` of its own, and it is a <pre>, not a div. The radius,
          border and padding are the family's. */}
      <pre className="rounded-lg border border-border p-4 min-w-0 bg-bg-muted overflow-x-auto text-xs font-mono text-text">
        <code>{code}</code>
      </pre>
    </div>
  )
}
