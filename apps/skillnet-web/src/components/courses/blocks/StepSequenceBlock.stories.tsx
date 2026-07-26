import type { Meta } from '@storybook/react-vite'
import { StepSequenceBlock } from './StepSequenceBlock'

const meta: Meta<typeof StepSequenceBlock> = {
  title: 'Courses/Blocks/StepSequenceBlock',
  component: StepSequenceBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const Procedimiento = () => (
  <div className="max-w-2xl">
    <StepSequenceBlock
      title="Proceso de devolucion"
      steps={[
        'Verificar el producto',
        'Escanear el ticket',
        'Registrar en el sistema',
        'Emitir el reembolso',
      ]}
    />
  </div>
)

export const PasosLargos = () => (
  <div className="max-w-md">
    <StepSequenceBlock
      title="Incidencia de proveedor"
      steps={[
        'Fotografiar el producto y el numero de lote antes de retirarlo del lineal, porque el proveedor lo pide siempre',
        'Abrir la incidencia en el terminal con el codigo **INC-PROV**',
        'Entregar al cliente el vale y explicarle que el importe no cambia',
      ]}
    />
  </div>
)
