import type { Meta } from '@storybook/react-vite'
import { CalloutBlock } from './CalloutBlock'

const meta: Meta<typeof CalloutBlock> = {
  title: 'Courses/Blocks/CalloutBlock',
  component: CalloutBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const Tonos = () => (
  <div className="space-y-4 max-w-2xl">
    <CalloutBlock
      tone="info"
      text="El plazo se cuenta desde la fecha del ticket, no desde la entrega."
    />
    <CalloutBlock
      tone="warn"
      text="Nunca aceptes una devolucion de producto refrigerado, ni dentro de plazo."
    />
    <CalloutBlock
      tone="success"
      text="Si el producto llego en mal estado se tramita como incidencia de proveedor y el cliente cobra igual."
    />
  </div>
)
