import type { Meta } from '@storybook/react-vite'
import { DiagramBuilderBlock } from './DiagramBuilderBlock'

const meta: Meta<typeof DiagramBuilderBlock> = {
  title: 'Courses/Blocks/DiagramBuilderBlock',
  component: DiagramBuilderBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const ProcesoLineal = () => (
  <div className="max-w-lg">
    <DiagramBuilderBlock
      title="Proceso de devolucion"
      steps={[
        {
          label: 'Recepcion',
          svgFragment: '<rect x="10" y="120" width="100" height="60" rx="8" fill="#e2e8f0" stroke="#64748b" stroke-width="2"/><text x="60" y="155" text-anchor="middle" font-size="12" fill="#334155">Recepcion</text>',
          explanation: 'El cliente presenta el producto y el ticket de compra.',
        },
        {
          label: 'Verificacion',
          svgFragment: '<line x1="110" y1="150" x2="150" y2="150" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"/><rect x="150" y="120" width="100" height="60" rx="8" fill="#e2e8f0" stroke="#64748b" stroke-width="2"/><text x="200" y="155" text-anchor="middle" font-size="12" fill="#334155">Verificacion</text><defs><marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b"/></marker></defs>',
          explanation: 'Se comprueba el estado del producto y la validez del ticket.',
        },
        {
          label: 'Reembolso',
          svgFragment: '<line x1="250" y1="150" x2="290" y2="150" stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"/><rect x="290" y="120" width="100" height="60" rx="8" fill="#dbeafe" stroke="#3b82f6" stroke-width="2"/><text x="340" y="155" text-anchor="middle" font-size="12" fill="#1e40af">Reembolso</text>',
          explanation: 'Se emite el reembolso en el mismo medio de pago original.',
        },
      ]}
    />
  </div>
)

export const DosPasos = () => (
  <div className="max-w-lg">
    <DiagramBuilderBlock
      title="Apertura de caja"
      steps={[
        {
          label: 'Contar fondo',
          svgFragment: '<circle cx="100" cy="150" r="40" fill="#fef3c7" stroke="#f59e0b" stroke-width="2"/><text x="100" y="155" text-anchor="middle" font-size="11" fill="#92400e">Contar</text>',
          explanation: 'Contar el fondo de caja asignado y verificar que coincide con el registro.',
        },
        {
          label: 'Activar TPV',
          svgFragment: '<line x1="140" y1="150" x2="200" y2="150" stroke="#64748b" stroke-width="2"/><circle cx="250" cy="150" r="40" fill="#dcfce7" stroke="#22c55e" stroke-width="2"/><text x="250" y="155" text-anchor="middle" font-size="11" fill="#166534">TPV</text>',
          explanation: 'Encender el terminal de punto de venta y verificar la conexion.',
        },
      ]}
    />
  </div>
)
