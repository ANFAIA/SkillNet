import type { Meta } from '@storybook/react-vite'
import { SliderExplorationBlock } from './SliderExplorationBlock'

const meta: Meta<typeof SliderExplorationBlock> = {
  title: 'Courses/Blocks/SliderExplorationBlock',
  component: SliderExplorationBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const Lineal = () => (
  <div className="max-w-lg">
    <SliderExplorationBlock
      title="Funcion lineal"
      variable="x"
      min={0}
      max={10}
      step={1}
      formula="y = 2 * x + 3"
      description="Observa como cambia y al modificar x."
    />
  </div>
)

export const Porcentaje = () => (
  <div className="max-w-lg">
    <SliderExplorationBlock
      title="Calculo de IVA"
      variable="precio"
      min={0}
      max={1000}
      step={10}
      formula="total = precio * 1.21"
      description="Ajusta el precio base para ver el total con IVA (21%)."
    />
  </div>
)

export const SinFormula = () => (
  <div className="max-w-lg">
    <SliderExplorationBlock
      title="Temperatura"
      variable="temp"
      min={-20}
      max={50}
      step={0.5}
      formula=""
      description="Ajuste libre de temperatura."
    />
  </div>
)
