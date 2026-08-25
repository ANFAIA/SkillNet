/**
 * El verde y el rojo de una respuesta ya corregida.
 *
 * Reportado desde el producto: "ahi no se pone ni en verde ni en rojo cuando falla". El
 * panel de resultado si se pintaba; lo que no se pintaba eran las OPCIONES, y encima al
 * corregir perdian hasta el resaltado de la elegida (`selected === idx && !disabled`), asi
 * que la pantalla quedaba igual que antes de responder salvo por un texto.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { IntlProvider } from 'react-intl'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { QuizItemBlock } from './QuizItemBlock'
import { es as messages } from '../../../i18n/es'

vi.mock('../../../api/client', () => ({ post: vi.fn(), get: vi.fn() }))

// Importado despues del mock para coger el binding mockeado.
import { post } from '../../../api/client'

const mockedPost = vi.mocked(post)

const OPCIONES = ['La primera', 'La segunda', 'La tercera']

function renderQuiz() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <IntlProvider locale="es" messages={messages}>
        <QuizItemBlock
          item_id="q1"
          item_type="test"
          bloom_level="understand"
          question="Cual es?"
          options={OPCIONES}
          nodeId="node-1"
          renderId="render-1"
        />
      </IntlProvider>
    </QueryClientProvider>,
  )
}

/**
 * El panel tappable de una opcion, por su posicion.
 *
 * Se busca por el radio y no por el texto: cuando el servidor revela la solucion, ese
 * mismo texto tambien aparece en el bloque de solucion, y buscarlo por texto encuentra
 * dos elementos.
 */
function opcion(idx: number): HTMLElement {
  const label = screen.getAllByRole('radio')[idx]?.closest('label')
  if (!label) throw new Error(`sin panel para la opcion ${idx}`)
  return label
}

async function responde(texto: string) {
  await userEvent.click(screen.getByText(texto))
  await userEvent.click(screen.getByRole('button', { name: /comprobar/i }))
}

beforeEach(() => {
  mockedPost.mockReset()
})

describe('QuizItemBlock: la correccion se ve en la opcion, no solo en el panel', () => {
  it('pinta en rojo la opcion elegida al fallar', async () => {
    mockedPost.mockResolvedValue({
      passed: false,
      feedback: 'Casi.',
      correct_answer: null,
      show_worked_solution: false,
    })
    renderQuiz()

    await responde('La segunda')

    await waitFor(() => expect(opcion(1).className).toContain('border-danger'))
    expect(opcion(1).className).not.toContain('border-primary')
  })

  it('pinta en verde la opcion elegida al acertar', async () => {
    mockedPost.mockResolvedValue({
      passed: true,
      feedback: 'Eso es.',
      correct_answer: null,
      show_worked_solution: false,
    })
    renderQuiz()

    await responde('La primera')

    await waitFor(() => expect(opcion(0).className).toContain('border-accent'))
  })

  it('marca la correcta en verde cuando el servidor la revela, sin tocar las demas', async () => {
    mockedPost.mockResolvedValue({
      passed: false,
      feedback: 'Se acabaron los intentos.',
      correct_answer: { correct: 2 },
      show_worked_solution: true,
    })
    renderQuiz()

    await responde('La primera')

    await waitFor(() => expect(opcion(0).className).toContain('border-danger'))
    expect(opcion(2).className).toContain('border-accent')
    expect(opcion(1).className).not.toContain('border-accent')
    expect(opcion(1).className).not.toContain('border-danger')
  })

  it('no adelanta ningun color antes de responder', () => {
    renderQuiz()
    for (let i = 0; i < OPCIONES.length; i += 1) {
      expect(opcion(i).className).not.toContain('border-accent')
      expect(opcion(i).className).not.toContain('border-danger')
    }
  })
})
