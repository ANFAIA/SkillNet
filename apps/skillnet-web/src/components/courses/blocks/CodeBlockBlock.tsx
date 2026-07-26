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
        <p className="text-xs font-mono text-text-muted mb-1.5">{language}</p>
      ) : null}
      <pre className="rounded-lg bg-bg-muted border border-border p-3 overflow-x-auto text-xs font-mono text-text">
        <code>{code}</code>
      </pre>
    </div>
  )
}
