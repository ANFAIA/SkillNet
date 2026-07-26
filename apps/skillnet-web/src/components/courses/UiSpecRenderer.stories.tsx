import type { Meta } from '@storybook/react-vite'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { UiSpecRenderer } from './UiSpecRenderer'

// Inline programs rather than the backend fixture files: these stories run in a
// browser (the `storybook` vitest project), where `node:fs` does not exist. The
// unit suite is what runs against the canonical `.openui` corpus.
const PROGRAMS: Record<string, string> = {
  explanation_basic: [
    'root = Stack([intro, pasos], "md")',
    'intro = TextContent("Las devoluciones se aceptan durante 30 dias naturales.", "lead")',
    'pasos = StepSequence("Proceso de devolucion", ["Verificar el producto", "Escanear el ticket", "Registrar en el sistema", "Emitir el reembolso"])',
  ].join('\n'),
  explanation_callout_first: [
    'root = Stack([aviso, cuerpo, tabla], "lg")',
    'aviso = Callout("warn", "Pasados 30 dias aplica la garantia del fabricante, no la devolucion.")',
    'cuerpo = TextContent("El plazo se cuenta desde la fecha impresa en el ticket.", "body")',
    'tabla = Table(["Caso", "Accion"], [["Menos de 30 dias", "Devolucion"], ["Mas de 30 dias", "Garantia"]])',
  ].join('\n'),
  card_nested: [
    'root = Stack([intro, ficha], "md")',
    'intro = TextContent("El script comprueba el plazo antes de aceptar la devolucion.", "lead")',
    'ficha = Card("Comprobacion del plazo", [texto, codigo])',
    'texto = TextContent("Compara la fecha del ticket con la de hoy.", "body")',
    'codigo = CodeBlock("python", "dias = (hoy - ticket).days\\nif dias <= 30:\\n    aceptar()")',
  ].join('\n'),
  chart_data: [
    'root = Stack([intro, grafico], "md")',
    'intro = TextContent("Variacion de las devoluciones en la tienda de Bilbao.", "lead")',
    'grafico = Chart("bar", "Variacion mensual de devoluciones", ["Enero", "Febrero", "Marzo"], [12, 8.5, -3])',
  ].join('\n'),
  mixed_quiz: [
    'root = Stack([intro, quiz], "md")',
    'intro = TextContent("Las devoluciones se aceptan durante 30 dias naturales.", "lead")',
    'quiz = QuizItem("q1", "test", "apply", "Un cliente vuelve el dia 32. Que haces?", ["Aceptar la devolucion", "Ofrecer garantia del fabricante", "Rechazar sin mas", "Llamar al encargado"])',
  ].join('\n'),
  fallback_markdown: [
    'root = Stack([semilla], "md")',
    'semilla = Markdown("## Devoluciones\\n\\nSe aceptan durante **30 dias naturales**.")',
  ].join('\n'),
}

const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })

const meta: Meta<typeof UiSpecRenderer> = {
  title: 'Courses/UiSpecRenderer',
  component: UiSpecRenderer,
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

/** One program per frozen kit component, rendered by OpenUI's runtime. */
export const Programas = () => (
  <div className="space-y-10">
    {Object.entries(PROGRAMS).map(([name, program]) => (
      <section key={name}>
        <p className="text-xs font-mono text-text-muted mb-3">{name}</p>
        <UiSpecRenderer program={program} nodeId="node-demo" renderId="render-demo" />
      </section>
    ))}
  </div>
)

/** Half-written input, the way it arrives over SSE: the shell first, then the blocks. */
export const Streaming = () => {
  const full = PROGRAMS.explanation_basic
  return (
    <div className="space-y-10">
      {[34, 120, full.length].map((cut) => (
        <section key={cut}>
          <p className="text-xs font-mono text-text-muted mb-3">{cut} caracteres recibidos</p>
          <UiSpecRenderer program={full.slice(0, cut)} nodeId="node-demo" isStreaming />
        </section>
      ))}
    </div>
  )
}

/**
 * What a broken program looks like. None of these can reach a real learner — the
 * backend validator rejects them — but the renderer degrades instead of blanking
 * the screen, and that is the behaviour worth being able to see.
 */
export const ProgramasRotos = () => (
  <div className="space-y-10">
    <section>
      <p className="text-xs font-mono text-text-muted mb-3">
        referencia colgante · el hijo inexistente se omite
      </p>
      <UiSpecRenderer
        program={
          'root = Stack([b1, ausente, b2], "md")\n' +
          'b1 = TextContent("Primer bloque, si se ve.", "lead")\n' +
          'b2 = TextContent("Segundo bloque, tambien se ve.", "body")'
        }
        nodeId="node-demo"
      />
    </section>
    <section>
      <p className="text-xs font-mono text-text-muted mb-3">
        ciclo · el arbol se corta, los hermanos siguen
      </p>
      <UiSpecRenderer
        program={
          'root = Stack([antes, ciclo], "md")\n' +
          'antes = TextContent("Bloque valido antes del ciclo.", "lead")\n' +
          'ciclo = Card("Se referencia a si mismo", [ciclo])'
        }
        nodeId="node-demo"
      />
    </section>
    <section>
      <p className="text-xs font-mono text-text-muted mb-3">
        fuera de catalogo · Timeline no se pinta, la pantalla no se cae
      </p>
      <UiSpecRenderer
        program={
          'root = Stack([intro, linea], "md")\n' +
          'intro = TextContent("Los hitos del proceso de devolucion.", "lead")\n' +
          'linea = Timeline("Hitos", ["Compra", "Devolucion", "Reembolso"])'
        }
        nodeId="node-demo"
      />
    </section>
    <section>
      <p className="text-xs font-mono text-text-muted mb-3">
        reactividad · la puerta estatica no pinta NADA (y registra el incidente)
      </p>
      <UiSpecRenderer
        program={
          '$elegida = -1\n' +
          'root = Stack([intro], "md")\n' +
          'intro = TextContent("Esto no deberia llegar nunca al navegador.", "lead")'
        }
        nodeId="node-demo"
      />
    </section>
  </div>
)
