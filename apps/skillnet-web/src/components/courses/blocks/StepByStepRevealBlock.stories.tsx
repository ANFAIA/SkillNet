import type { Meta } from '@storybook/react-vite'
import { StepByStepRevealBlock } from './StepByStepRevealBlock'

const meta: Meta<typeof StepByStepRevealBlock> = {
  title: 'Courses/Blocks/StepByStepRevealBlock',
  component: StepByStepRevealBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const ProcesoDevolucion = () => (
  <div className="max-w-2xl">
    <StepByStepRevealBlock
      title="Proceso de devolucion paso a paso"
      steps={[
        { statement: 'Verificar el estado del producto', explanation: 'Comprobar que el producto esta en condiciones de ser devuelto: sin uso evidente, con etiquetas y en su embalaje original si lo tiene.' },
        { statement: 'Escanear el ticket de compra', explanation: 'Usar el lector para localizar la transaccion original. Si el cliente no tiene ticket, buscar por tarjeta de fidelidad o DNI.' },
        { statement: 'Registrar la devolucion en el sistema', explanation: 'Seleccionar el motivo de devolucion del menu desplegable. El sistema calculara automaticamente el importe a reembolsar.' },
        { statement: 'Emitir el reembolso', explanation: 'El reembolso se hace siempre en el mismo medio de pago original. Efectivo: devolver en caja. Tarjeta: el abono tarda 3-5 dias.' },
        { statement: 'Entregar el justificante al cliente', explanation: 'Imprimir el justificante de devolucion y entregarlo. Informar del plazo si fue con tarjeta.' },
      ]}
    />
  </div>
)

export const DosPasos = () => (
  <div className="max-w-2xl">
    <StepByStepRevealBlock
      title="Cierre rapido de caja"
      steps={[
        { statement: 'Contar el efectivo', explanation: 'Separar billetes y monedas. Anotar el total en la hoja de cierre.' },
        { statement: 'Cuadrar con el sistema', explanation: 'Comparar el total fisico con el registrado en el TPV. Una diferencia menor a 2 euros se considera aceptable.' },
      ]}
    />
  </div>
)

export const UnPaso = () => (
  <div className="max-w-2xl">
    <StepByStepRevealBlock
      title="Activar la alarma"
      steps={[
        { statement: 'Introducir el codigo en el panel', explanation: 'El codigo de 4 digitos esta en el sobre cerrado del encargado. Tienes 30 segundos desde que cierras la puerta.' },
      ]}
    />
  </div>
)
