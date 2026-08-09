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
    <ClickableText as="div" className="min-w-0 rounded-lg border border-border overflow-hidden">
      {/* `tabIndex` no es adorno: una region que desplaza y no se puede enfocar deja la
          mitad derecha de la tabla fuera del alcance de quien navega con teclado
          (axe `scrollable-region-focusable`). Antes no saltaba porque `overflow-hidden`
          impedia el scroll del todo — la tabla ancha se recortaba en vez de desplazarse. */}
      <div className="overflow-x-auto [scrollbar-gutter:auto]" tabIndex={0} role="group" aria-label="Tabla">
        {/* `w-full`, y el ancho lo resuelve el salto de linea de las celdas. El fondo de
            las filas se quedaba corto porque una celda traia una URL entera
            (`https://backend.ticketrona.com/dashboard`): una palabra que no se puede
            partir empuja la tabla mas alla de su caja y el `tr` deja de pintar ahi. Se
            arregla dejando que esa palabra se rompa, no haciendo la tabla mas ancha —
            `w-max` lo "arreglaba" quitando el salto de linea a TODAS las celdas, que
            convierte cualquier frase en una linea larguisima y manda la tabla al scroll.
            El envoltorio sigue desplazando por si algun dia llega una tabla de verdad
            ancha (muchas columnas), pero el caso normal ya no lo necesita. */}
        <table className="w-full text-sm border-collapse">
        {head.length > 0 && (
          <thead>
            <tr className="bg-bg-muted sticky top-0 z-10">
              {head.map((header, idx) => (
                <th
                  key={idx}
                  scope="col"
                  className="text-left align-top py-2.5 px-4 border-b border-border font-semibold text-text text-xs uppercase tracking-wide leading-relaxed [overflow-wrap:anywhere]"
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
                  className={`align-top py-2.5 px-4 text-text leading-relaxed [overflow-wrap:anywhere] ${
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
      </div>
    </ClickableText>
  )
}
