import type { Meta } from '@storybook/react-vite'
import { NodeSkeleton } from './NodeSkeleton'

/**
 * The wait, in the three shapes it can take (§9.2, §12.3).
 *
 * The `a11y` addon runs as `error` rather than `todo` for everything new: this component
 * is a live region that appears while the learner is looking at the screen, so a missing
 * `aria-busy` or a shimmer announced as content is a real defect, not a nit.
 */
const meta: Meta<typeof NodeSkeleton> = {
  title: 'Courses/NodeSkeleton',
  component: NodeSkeleton,
  parameters: { a11y: { test: 'error' } },
}
export default meta

/** Before `decide_formato` has spoken: prose is the shape of an unknown lesson. */
export const SinFormatoTodavia = () => (
  <div className="max-w-2xl">
    <NodeSkeleton message="Preparando el nodo..." />
  </div>
)

/** After the `ui_format` event: the skeleton takes the shape the lesson will have. */
export const Explicacion = () => (
  <div className="max-w-2xl">
    <NodeSkeleton format="explanation" message="Escribiendo la leccion..." blocksReady={2} />
  </div>
)

export const Ejercicio = () => (
  <div className="max-w-2xl">
    <NodeSkeleton format="exercise" message="Escribiendo la leccion..." blocksReady={1} />
  </div>
)

export const Grafico = () => (
  <div className="max-w-2xl">
    <NodeSkeleton format="chart" message="Revisando la leccion..." blocksReady={4} />
  </div>
)
