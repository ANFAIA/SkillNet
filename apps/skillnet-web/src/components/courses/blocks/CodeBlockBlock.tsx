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
 * Visual improvements: the language label is now a small badge pinned to the
 * top-right corner of the code slab (inside the border), and the background
 * uses a slightly darker shade for better contrast.
 */
export function CodeBlockBlock({ language, code }: CodeBlockBlockProps) {
  return (
    <div data-no-explain="" className="min-w-0 relative">
      <pre className="rounded-lg border border-border p-4 pt-5 min-w-0 bg-bg-muted overflow-x-auto text-[13px] leading-relaxed font-mono text-text">
        <code>{code}</code>
      </pre>
      {/* Language badge pinned to the top-right corner, inside the border radius */}
      {language ? (
        <span className="absolute top-2 right-2 px-2 py-0.5 rounded-md bg-bg-subtle border border-border text-[10px] font-mono font-medium text-text-muted select-none">
          {language}
        </span>
      ) : null}
    </div>
  )
}
