import type { Meta } from '@storybook/react-vite'
import { TableBlock } from './TableBlock'

const meta: Meta<typeof TableBlock> = {
  title: 'Courses/Blocks/TableBlock',
  component: TableBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const Comparativa = () => (
  <div className="max-w-2xl">
    <TableBlock
      headers={['Caso', 'Plazo', 'Documento']}
      rows={[
        ['Devolucion', '30 dias', 'Ticket'],
        ['Cambio de talla', '15 dias', 'Ticket'],
        ['Garantia del fabricante', '2 anos', 'Factura'],
      ]}
    />
  </div>
)

export const Estrecha = () => (
  <div className="max-w-xs border border-dashed border-border-strong p-2">
    <p className="text-xs text-text-muted mb-2">Contenedor estrecho: la tabla scrollea sola</p>
    <TableBlock
      headers={['Producto', 'Temperatura maxima', 'Accion si se supera']}
      rows={[
        ['Lacteos', '4 °C', 'Retirar y registrar incidencia'],
        ['Congelados', '-18 °C', 'Retirar sin excepcion'],
      ]}
    />
  </div>
)
