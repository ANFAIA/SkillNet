import type { Meta } from '@storybook/react-vite'
import { CardBlock } from './CardBlock'
import { TextContentBlock } from './TextContentBlock'
import { StepSequenceBlock } from './StepSequenceBlock'

const meta: Meta<typeof CardBlock> = {
  title: 'Courses/Blocks/CardBlock',
  component: CardBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const ConTexto = () => (
  <div className="max-w-2xl">
    <CardBlock title="Requisitos de la devolucion">
      <TextContentBlock text="El producto debe estar sin usar y con su embalaje original." />
      <TextContentBlock text="El ticket de compra es obligatorio, en papel o digital." />
    </CardBlock>
  </div>
)

export const ConProcedimiento = () => (
  <div className="max-w-2xl">
    <CardBlock title="Si el cliente no trae el ticket">
      <StepSequenceBlock
        title="Alternativa aceptada"
        steps={[
          'Pedir la tarjeta con la que pago',
          'Buscar la operacion en el terminal',
          'Emitir un vale por el importe',
        ]}
      />
    </CardBlock>
  </div>
)
