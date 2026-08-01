import type { Meta } from '@storybook/react-vite'
import { ManipulableGraphBlock } from './ManipulableGraphBlock'

const meta: Meta<typeof ManipulableGraphBlock> = {
  title: 'Courses/Blocks/ManipulableGraphBlock',
  component: ManipulableGraphBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const Seno = () => (
  <div className="max-w-xl">
    <ManipulableGraphBlock
      title="Funcion seno"
      xLabel="x"
      yLabel="y"
      points={[['Origen', '0', '0', 'false']]}
      functions={['Math.sin(x)']}
    />
  </div>
)

export const Cuadratica = () => (
  <div className="max-w-xl">
    <ManipulableGraphBlock
      title="Parabola y puntos"
      xLabel="x"
      yLabel="f(x)"
      points={[
        ['A', '-2', '4', 'true'],
        ['B', '0', '0', 'false'],
        ['C', '2', '4', 'true'],
      ]}
      functions={['x*x']}
    />
  </div>
)

export const SinFunciones = () => (
  <div className="max-w-xl">
    <ManipulableGraphBlock
      title="Plano vacio con puntos"
      xLabel="eje X"
      yLabel="eje Y"
      points={[
        ['P1', '1', '3', 'true'],
        ['P2', '-1', '-2', 'true'],
      ]}
      functions={[]}
    />
  </div>
)
