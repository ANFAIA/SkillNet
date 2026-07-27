import type { Meta } from '@storybook/react-vite'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StackBlock } from './StackBlock'
import { TextContentBlock } from './TextContentBlock'
import { CalloutBlock } from './CalloutBlock'
import { CardBlock } from './CardBlock'
import { ChartBlock } from './ChartBlock'
import { CodeBlockBlock } from './CodeBlockBlock'
import { StepSequenceBlock } from './StepSequenceBlock'
import { TableBlock } from './TableBlock'
import { QuizItemBlock } from './QuizItemBlock'

const meta: Meta<typeof StackBlock> = {
  title: 'Courses/Blocks/StackBlock',
  component: StackBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

const Sample = () => (
  <>
    <TextContentBlock text="Primer bloque de la pantalla." variant="lead" />
    <TextContentBlock text="Segundo bloque, cuerpo de la explicacion." variant="body" />
    <TextContentBlock text="Manual de atencion al cliente, pagina 3." variant="caption" />
  </>
)

export const Separaciones = () => (
  <div className="space-y-8 max-w-2xl">
    {(['sm', 'md', 'lg'] as const).map((gap) => (
      <div key={gap}>
        <p className="text-xs text-text-muted mb-2">gap=&quot;{gap}&quot;</p>
        <StackBlock gap={gap}>
          <Sample />
        </StackBlock>
      </div>
    ))}
  </div>
)

// `QuizItemBlock` is autonomous (§5.3) and owns its mutation, so the family needs a
// client even though a story renders it read-only (no `renderId`, nothing is posted).
const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })

/**
 * Every kit component in one Stack, then most of them again in a different order.
 *
 * This is the story the family is judged on. The blocks are generated in whatever
 * sequence the model chooses, so each one looking right on its own page proves
 * nothing — what has to hold is that a Callout above a Table above a Chart lines up
 * with a Callout *below* them. Read down the left edge: the block titles should all
 * sit at the same size and leave the same gap under themselves, and the panelled
 * blocks (Callout, QuizItem, the code slab) should share one radius and one padding,
 * with `Card` deliberately one size larger because it contains them.
 */
export const Familia = () => (
  <QueryClientProvider client={client}>
    <div className="space-y-10 max-w-2xl">
      <StackBlock gap="md">
        <TextContentBlock
          text="Esto te sirve para resolver una devolucion en el mostrador sin llamar al encargado."
          variant="lead"
        />
        <CalloutBlock
          tone="warn"
          text="Nunca aceptes una devolucion de producto refrigerado, ni dentro de plazo."
        />
        <StepSequenceBlock
          title="Como se tramita"
          steps={['Pedir el ticket', 'Comprobar el estado del producto', 'Emitir el abono']}
        />
        <TableBlock
          headers={['Caso', 'Plazo', 'Documento']}
          rows={[
            ['Compra en tienda', '30 dias', 'Ticket'],
            ['Compra online', '14 dias', 'Albaran o correo de confirmacion del pedido'],
          ]}
        />
        <CardBlock title="Si el cliente no trae el ticket">
          <TextContentBlock text="Se busca la operacion por la tarjeta con la que pago." />
          <CodeBlockBlock language="terminal" code="buscar --tarjeta 4539****1234 --dias 30" />
        </CardBlock>
        <ChartBlock
          kind="bar"
          title="Motivos de devolucion el mes pasado"
          labels={['Talla', 'Defecto', 'Fuera de plazo']}
          values={[42, 17, 6]}
        />
        <QuizItemBlock
          item_id="demo"
          item_type="test"
          bloom_level="apply"
          question="Un cliente vuelve a los 20 dias con el ticket. Que aplicas?"
          options={['Devolucion', 'Garantia del fabricante', 'Nada']}
          nodeId="demo"
        />
        <TextContentBlock text="Manual de atencion al cliente, pagina 3." variant="caption" />
      </StackBlock>

      <StackBlock gap="md">
        <QuizItemBlock
          item_id="demo-2"
          item_type="true_false"
          bloom_level="understand"
          question="El plazo se cuenta desde la entrega, no desde el ticket."
          nodeId="demo"
        />
        <ChartBlock
          kind="line"
          title="Devoluciones por semana"
          labels={['S1', 'S2', 'S3', 'S4']}
          values={[12, 19, 9, 14]}
        />
        <CalloutBlock tone="info" text="El plazo se cuenta desde la fecha del ticket." />
        <CalloutBlock
          tone="success"
          text="Si el producto llego en mal estado se tramita como incidencia de proveedor."
        />
        <StepSequenceBlock title="Cierre" steps={['Archivar el abono', 'Avisar al encargado']} />
      </StackBlock>
    </div>
  </QueryClientProvider>
)
