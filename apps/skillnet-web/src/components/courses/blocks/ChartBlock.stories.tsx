import type { Meta } from '@storybook/react-vite'
import { ChartBlock } from './ChartBlock'

const meta: Meta<typeof ChartBlock> = {
  title: 'Courses/Blocks/ChartBlock',
  component: ChartBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const Barras = () => (
  <div className="max-w-lg">
    <ChartBlock
      kind="bar"
      title="Motivos de devolucion (ultimo trimestre)"
      labels={['Talla', 'Defecto', 'Ya no lo quiere', 'Regalo duplicado']}
      values={[148, 62, 41, 19]}
    />
  </div>
)

export const Linea = () => (
  <div className="max-w-lg">
    <ChartBlock
      kind="line"
      title="Devoluciones por mes"
      labels={['Enero', 'Febrero', 'Marzo', 'Abril']}
      values={[92, 118, 60, 74]}
    />
  </div>
)

export const SinDatos = () => (
  <div className="max-w-lg">
    <ChartBlock kind="bar" title="Motivos de devolucion" labels={[]} values={[]} />
  </div>
)
