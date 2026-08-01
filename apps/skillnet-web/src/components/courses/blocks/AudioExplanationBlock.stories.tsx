import type { Meta } from '@storybook/react-vite'
import { AudioExplanationBlock } from './AudioExplanationBlock'

const meta: Meta<typeof AudioExplanationBlock> = {
  title: 'Courses/Blocks/AudioExplanationBlock',
  component: AudioExplanationBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const VozNeutral = () => (
  <div className="max-w-lg">
    <AudioExplanationBlock
      text="Las devoluciones se aceptan durante 30 dias naturales desde la fecha de compra. El producto debe estar en su estado original."
      voice="neutral"
    />
  </div>
)

export const VozCalida = () => (
  <div className="max-w-lg">
    <AudioExplanationBlock
      text="Recuerda saludar al cliente con una sonrisa y ofrecerle ayuda de manera proactiva."
      voice="warm"
    />
  </div>
)

export const VozFormal = () => (
  <div className="max-w-lg">
    <AudioExplanationBlock
      text="El incumplimiento de la normativa de proteccion de datos puede conllevar sanciones administrativas."
      voice="formal"
    />
  </div>
)
