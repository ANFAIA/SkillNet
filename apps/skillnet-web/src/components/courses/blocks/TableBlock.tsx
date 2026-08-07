import { InlineMarkdown } from './InlineMarkdown'
import { ClickableText } from '../ClickableText'

export interface TableBlockProps {
  headers: string[]
  rows: string[][]
}

/**
 * Comparison table. Same visual language as the markdown tables in
 * `LessonContent`, so a v1 lesson and a v2 spec do not look like two products.
 * The wrapper scrolls on its own — the page body never scrolls sideways.
 *
 * §8.5: one `ClickableText` for the table, so it is one tab stop rather than one
 * per cell. `BLOCK_SELECTOR` includes `td` and `th`, so a clicked word still
 * sends its own cell as context and not the whole grid.
 */
export function TableBlock({ headers, rows }: TableBlockProps) {
  const head = Array.isArray(headers) ? headers : []
  const body = Array.isArray(rows) ? rows : []

  return (
    <ClickableText as="div" className="overflow-x-auto min-w-0 rounded-lg border border-border overflow-hidden [scrollbar-gutter:auto]">
      <table className="w-full text-sm border-collapse">
        {head.length > 0 && (
          <thead>
            <tr className="bg-bg-muted sticky top-0 z-10">
              {head.map((header, idx) => (
                <th
                  key={idx}
                  scope="col"
                  className="text-left align-top py-2.5 px-4 border-b border-border font-semibold text-text text-xs uppercase tracking-wide leading-relaxed"
                >
                  <InlineMarkdown>{header}</InlineMarkdown>
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {body.map((row, rowIdx) => (
            <tr
              key={rowIdx}
              className={`transition-colors duration-150 hover:bg-primary-subtle ${
                rowIdx % 2 === 1 ? 'bg-bg-subtle' : 'bg-bg'
              }`}
            >
              {(Array.isArray(row) ? row : []).map((cell, cellIdx) => (
                <td
                  key={cellIdx}
                  // `leading-relaxed` matches the prose blocks: a two-line cell used
                  // to set tighter than the paragraph right above the table.
                  className={`align-top py-2.5 px-4 text-text leading-relaxed ${
                    cellIdx === 0 ? 'font-medium' : ''
                  } ${rowIdx < body.length - 1 ? 'border-b border-border' : ''}`}
                >
                  <InlineMarkdown>{String(cell ?? '')}</InlineMarkdown>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </ClickableText>
  )
}
