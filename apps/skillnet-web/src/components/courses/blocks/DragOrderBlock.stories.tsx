import type { Meta } from '@storybook/react-vite'
import { DragOrderBlock } from './DragOrderBlock'

const meta: Meta<typeof DragOrderBlock> = {
  title: 'Courses/Blocks/DragOrderBlock',
  component: DragOrderBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const ProcesoDevolucion = () => (
  <div className="max-w-md">
    <DragOrderBlock
      instruction="Ordena los pasos del proceso de devolucion"
      items={['Emitir el reembolso', 'Verificar el producto', 'Registrar en el sistema', 'Escanear el ticket']}
      correctOrder={['Verificar el producto', 'Escanear el ticket', 'Registrar en el sistema', 'Emitir el reembolso']}
    />
  </div>
)

export const DosPasos = () => (
  <div className="max-w-md">
    <DragOrderBlock
      instruction="Cual es el orden correcto?"
      items={['Cerrar la caja', 'Contar el efectivo']}
      correctOrder={['Contar el efectivo', 'Cerrar la caja']}
    />
  </div>
)

export const SeisPasos = () => (
  <div className="max-w-md">
    <DragOrderBlock
      instruction="Ordena el procedimiento de apertura de tienda"
      items={[
        'Encender la iluminacion',
        'Revisar el correo de incidencias',
        'Contar el fondo de caja',
        'Abrir la puerta principal',
        'Verificar la alarma',
        'Activar el TPV',
      ]}
      correctOrder={[
        'Verificar la alarma',
        'Encender la iluminacion',
        'Revisar el correo de incidencias',
        'Contar el fondo de caja',
        'Activar el TPV',
        'Abrir la puerta principal',
      ]}
    />
  </div>
)
