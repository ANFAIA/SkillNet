import type { Meta } from '@storybook/react-vite'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { QuizItemBlock } from './QuizItemBlock'

// The block is autonomous (§5.3): it owns its mutation, so it needs a client.
// Requests will fail in Storybook, which is itself a state worth seeing.
const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })

const meta: Meta<typeof QuizItemBlock> = {
  title: 'Courses/Blocks/QuizItemBlock',
  component: QuizItemBlock,
  parameters: { a11y: { test: 'error' } },
  decorators: [
    (Story) => (
      <QueryClientProvider client={client}>
        <div className="max-w-2xl">
          <Story />
        </div>
      </QueryClientProvider>
    ),
  ],
}
export default meta

export const SeleccionUnica = () => (
  <QuizItemBlock
    item_id="q1"
    item_type="test"
    bloom_level="apply"
    question="Un cliente vuelve el dia 32. Que haces?"
    options={[
      'Aceptar la devolucion',
      'Ofrecer garantia del fabricante',
      'Rechazar sin mas',
      'Llamar al encargado',
    ]}
    nodeId="node-demo"
    renderId="render-demo"
  />
)

export const VerdaderoFalso = () => (
  <QuizItemBlock
    item_id="q2"
    item_type="true_false"
    bloom_level="understand"
    question="El plazo de devolucion se cuenta desde la fecha de entrega."
    nodeId="node-demo"
    renderId="render-demo"
  />
)

export const RespuestaConstruida = () => (
  <QuizItemBlock
    item_id="q3"
    item_type="practical_case"
    bloom_level="analyze"
    question="El cliente ha perdido el ticket pero pago con tarjeta. Explica como lo resolverias."
    nodeId="node-demo"
    renderId="render-demo"
  />
)

export const VistaPreviaSinRender = () => (
  <QuizItemBlock
    item_id="q4"
    item_type="test"
    bloom_level="apply"
    question="Sin render_id el item se muestra, pero no se puede corregir."
    options={['Opcion A', 'Opcion B']}
    nodeId="node-demo"
  />
)
