/**
 * El boton de nodo siguiente, sobre el runtime de verdad.
 *
 * `StackBlock.gate.test.tsx` prueba el mecanismo con un doble; este prueba que el dato
 * llega. Entre el `Stack` y el ejercicio hay tres capas que el stepper no ve —el
 * envoltorio del runtime de OpenUI, `QuizItemRenderer` y `QuizItemBlock`— y la etiqueta
 * `solvable` se calcula ANTES de todas ellas, sobre el programa parseado. Si alguna
 * version del paquete cambia la forma en que entrega los hijos, o si el `Stack` del kit
 * vuelve a rendirlos en bloque, este test es el que se entera.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { UiSpecRenderer } from './UiSpecRenderer'
import { nextNodeContext, stepperContext } from './blocks/StepperContext'

vi.mock('../../api/client', () => ({ post: vi.fn() }))

/** `mixed_quiz`: tres pasos, y el ultimo es el ejercicio. */
const PROGRAMA = [
  'root = Stack([intro, pasos, quiz], "md")',
  'intro = TextContent("Las devoluciones se aceptan durante 30 dias naturales.", "lead")',
  'pasos = StepSequence("Proceso de devolucion", ["Verificar el producto", "Escanear el ticket"])',
  'quiz = QuizItem("q1", "test", "apply", "Un cliente vuelve el dia 32. Que haces?", ["Aceptar", "Rechazar"])',
].join('\n')

const irAlSiguienteNodo = vi.fn()

function renderLeccion() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <nextNodeContext.Provider value={{ navigate: irAlSiguienteNodo, title: 'Nodo 2' }}>
        <stepperContext.Provider value={true}>
          <UiSpecRenderer program={PROGRAMA} nodeId="node-1" renderId="render-1" />
        </stepperContext.Provider>
      </nextNodeContext.Provider>
    </QueryClientProvider>,
  )
}

const siguiente = () => screen.getByLabelText(/siguiente/i)
const ctaSiguienteNodo = () => screen.queryByRole('button', { name: 'Siguiente: Nodo 2' })

let warnSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
  irAlSiguienteNodo.mockReset()
})

afterEach(() => {
  warnSpy.mockRestore()
})

describe('el boton de nodo siguiente sobre el runtime de OpenUI', () => {
  it('no aparece nunca en un paso que termina en ejercicio sin resolver', async () => {
    // `ClickableText` (§8.5) parte la prosa en un `<span>` por palabra, asi que una
    // frase no tiene ningun elemento propio al que apuntar: se mira el subarbol.
    const { container } = renderLeccion()

    await userEvent.click(siguiente())
    await waitFor(() => expect(container).toHaveTextContent('Proceso de devolucion'))
    expect(ctaSiguienteNodo()).toBeNull()

    await userEvent.click(siguiente())
    // El ultimo paso. El `QuizItemBlock` todavia no ha montado —`AnimatePresence
    // mode="wait"` espera a la salida del anterior— y aun asi el paso ya esta cerrado.
    expect(container).not.toHaveTextContent('Un cliente vuelve')
    expect(ctaSiguienteNodo()).toBeNull()
    expect(siguiente()).toBeDisabled()

    await waitFor(() => expect(container).toHaveTextContent('Un cliente vuelve el dia 32'))
    expect(ctaSiguienteNodo()).toBeNull()
    expect(siguiente()).toBeDisabled()

    await userEvent.keyboard('{ArrowRight}')
    expect(irAlSiguienteNodo).not.toHaveBeenCalled()
  })

  it('lo enseña en un ultimo paso que no es ejercicio', async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <nextNodeContext.Provider value={{ navigate: irAlSiguienteNodo, title: 'Nodo 2' }}>
          <stepperContext.Provider value={true}>
            <UiSpecRenderer
              program={[
                'root = Stack([intro, cierre], "md")',
                'intro = TextContent("Uno.", "lead")',
                'cierre = TextContent("Dos.", "body")',
              ].join('\n')}
              nodeId="node-1"
              renderId="render-1"
            />
          </stepperContext.Provider>
        </nextNodeContext.Provider>
      </QueryClientProvider>,
    )

    await userEvent.click(siguiente())
    expect(ctaSiguienteNodo()).toBeInTheDocument()
  })
})
