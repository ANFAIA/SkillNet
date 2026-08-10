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
 *
 * A calm code slab: a hairline-outlined panel on the `bg-bg-muted` surface tone,
 * with the language as a quiet eyebrow in its own header strip (divided by the
 * same 1px border) rather than a badge floating over the first line of code. The
 * muted surface + full-contrast text read cleanly in both lesson modes.
 */
export function CodeBlockBlock({ language, code }: CodeBlockBlockProps) {
  return (
    <div
      data-no-explain=""
      className="min-w-0 overflow-hidden rounded-xl border border-border bg-bg-muted"
    >
      {language ? (
        <div className="flex items-center border-b border-border px-4 py-2">
          <span className={`${BLOCK_EYEBROW} mb-0 font-mono lowercase text-text-muted`}>
            {language}
          </span>
        </div>
      ) : null}
      <pre className="min-w-0 overflow-x-auto p-4 font-mono text-[13px] leading-relaxed text-text">
        <code>{code}</code>
      </pre>
    </div>
  )
}
