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
    // Dos envoltorios, y cada uno hace UNA cosa. Juntarlos era el defecto: `overflow-hidden`
    // es la forma corta y pisa el eje X, asi que recortaba el scroll que `overflow-x-auto`
    // pedia en el mismo elemento.
    // A calm panel, not a data grid: one soft surface, a barely-there border, a
    // large radius, and faint row dividers instead of zebra stripes or a boxed
    // grid (the "composed, not dumped" reference). The header is a quiet label
    // row, not a shouted uppercase bar.
    <ClickableText as="div" className="w-full min-w-0 rounded-xl border border-border bg-bg-subtle overflow-hidden">
      {/* `tabIndex` no es adorno: una region que desplaza y no se puede enfocar deja la
          mitad derecha de la tabla fuera del alcance de quien navega con teclado
          (axe `scrollable-region-focusable`). Antes no saltaba porque `overflow-hidden`
          impedia el scroll del todo — la tabla ancha se recortaba en vez de desplazarse. */}
      <div className="w-full overflow-x-auto [scrollbar-gutter:auto]" tabIndex={0} role="group" aria-label="Tabla">
        {/* `w-full`, y el ancho lo resuelve el salto de linea de las celdas. Una palabra
            que no se puede partir (una URL entera) empuja la tabla mas alla de su caja;
            se arregla dejando que esa palabra se rompa (`overflow-wrap:anywhere`), no
            haciendo la tabla mas ancha. El envoltorio sigue desplazando por si algun dia
            llega una tabla de verdad ancha (muchas columnas). */}
        {/* `w-full` sobre la tabla: con `table-auto` el navegador reparte el ancho
            sobrante del panel entre las columnas, asi que la tabla llena hasta el
            borde sin banda oscura a la derecha. Forzar una sola columna a `100%`
            colapsaba las demas a una letra por linea (con `overflow-wrap:anywhere`),
            asi que NO se hace: el reparto natural es el correcto. */}
        <table className="w-full border-collapse table-auto">
        {head.length > 0 && (
          <thead>
            <tr className="sticky top-0 z-10 bg-bg-muted">
              {head.map((header, idx) => (
                <th
                  key={idx}
                  scope="col"
                  className="text-left align-top py-3 px-5 border-b border-border font-medium text-text-secondary text-lesson-caption [overflow-wrap:anywhere]"
                >
                  <InlineMarkdown>{header}</InlineMarkdown>
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {body.map((row, rowIdx) => (
            <tr key={rowIdx}>
              {(Array.isArray(row) ? row : []).map((cell, cellIdx) => (
                <td
                  key={cellIdx}
                  className={`align-top py-3 px-5 text-lesson-body [overflow-wrap:anywhere] ${
                    cellIdx === 0 ? 'font-medium text-text' : 'text-text-secondary'
                  } ${rowIdx < body.length - 1 ? 'border-b border-border' : ''}`}
                >
                  <InlineMarkdown>{String(cell ?? '')}</InlineMarkdown>
                </td>
              ))}
            </tr>
          ))}
          </tbody>
        </table>
      </div>
    </ClickableText>
  )
}
