/**
 * La solucion que el servidor manda se ENSEÑA.
 *
 * Encontrado en una auditoria: `routes/nodes.py` revela `correct_answer` en tres casos
 * —acertar, agotar la cuota de pistas, o que salte la solucion trabajada— y este bloque
 * solo pintaba el panel en el tercero (`show_worked_solution`). En `test` y `true_false`
 * la opcion correcta se marcaba igualmente en verde, asi que el agujero solo se veia en
 * los otros cuatro tipos: el aprendiz gastaba las tres pistas, leia "te enseñaremos la
 * solucion", fallaba, y la solucion llegaba por el cable y se tiraba.
 *
 * El segundo caso es el reverso: cerrado SIN nada que enseñar. La clave de un item
 * abierto es una rubrica, que con razon no se expone, asi que ahi no hay respuesta que
 * dar — y eso se dice, en vez de dejar al aprendiz pasando de pantalla sin saberlo.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { IntlProvider } from 'react-intl'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { QuizItemBlock } from './QuizItemBlock'
import { stepperSolveContext } from './StepperContext'
import { es as messages } from '../../../i18n/es'
import type { ExerciseType } from '../../../types'

vi.mock('../../../api/client', () => ({ post: vi.fn(), get: vi.fn() }))

// Importado despues del mock para coger el binding mockeado.
import { post } from '../../../api/client'

const mockedPost = vi.mocked(post)

const SOLUTION_TITLE = messages['hints.solutionTitle']
const NO_SOLUTION = messages['activity.solutionUnavailable']

function renderQuiz({
  itemType,
  options,
  solveStep,
}: {
  itemType: ExerciseType
  options?: string[]
  solveStep?: () => void
}) {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <IntlProvider locale="es" messages={messages}>
        <stepperSolveContext.Provider value={solveStep ?? null}>
          <QuizItemBlock
            item_id="q1"
            item_type={itemType}
            bloom_level="apply"
            question="Que ocurre?"
            options={options ?? []}
            nodeId="node-1"
            renderId="render-1"
          />
        </stepperSolveContext.Provider>
      </IntlProvider>
    </QueryClientProvider>,
  )
}

/** Escribe una respuesta construida y la manda. */
async function respondeTexto(texto: string) {
  await userEvent.type(screen.getByRole('textbox'), texto)
  await userEvent.click(screen.getByRole('button', { name: /comprobar/i }))
}

beforeEach(() => {
  mockedPost.mockReset()
})

describe('QuizItemBlock: la solucion revelada por la cuota de pistas', () => {
  it('enseña la solucion de un fill_blank aunque no salte show_worked_solution', async () => {
    mockedPost.mockResolvedValue({
      passed: false,
      feedback: 'No es eso.',
      correct_answer: { blanks: ['fotosintesis'], explanation: 'La hoja convierte luz.' },
      show_worked_solution: false,
    })
    renderQuiz({ itemType: 'fill_blank' })

    await respondeTexto('respiracion')

    await waitFor(() => expect(screen.getByText(SOLUTION_TITLE)).toBeTruthy())
    expect(screen.getByText(/fotosintesis/)).toBeTruthy()
    expect(screen.getByText('La hoja convierte luz.')).toBeTruthy()
  })

  it('cierra el item cuando la solucion ya esta en pantalla: sin reintentar', async () => {
    mockedPost.mockResolvedValue({
      passed: false,
      feedback: 'No es eso.',
      correct_answer: { blanks: ['fotosintesis'] },
      show_worked_solution: false,
    })
    renderQuiz({ itemType: 'fill_blank' })

    await respondeTexto('respiracion')

    await waitFor(() => expect(screen.getByText(SOLUTION_TITLE)).toBeTruthy())
    expect(screen.queryByRole('button', { name: /reintentar/i })).toBeNull()
  })

  it('abre el paso al revelar, para no encerrar al aprendiz con la solucion', async () => {
    const solveStep = vi.fn()
    mockedPost.mockResolvedValue({
      passed: false,
      feedback: 'No es eso.',
      correct_answer: { blanks: ['fotosintesis'] },
      show_worked_solution: false,
    })
    renderQuiz({ itemType: 'fill_blank', solveStep })

    await respondeTexto('respiracion')

    await waitFor(() => expect(solveStep).toHaveBeenCalled())
  })

  it('sigue dejando reintentar cuando no llega ninguna solucion', async () => {
    const solveStep = vi.fn()
    mockedPost.mockResolvedValue({
      passed: false,
      feedback: 'Casi.',
      correct_answer: null,
      show_worked_solution: false,
    })
    renderQuiz({ itemType: 'fill_blank', solveStep })

    await respondeTexto('respiracion')

    await waitFor(() => expect(screen.getByRole('button', { name: /reintentar/i })).toBeTruthy())
    expect(screen.queryByText(SOLUTION_TITLE)).toBeNull()
    expect(screen.queryByText(NO_SOLUTION)).toBeNull()
    expect(solveStep).not.toHaveBeenCalled()
  })

  it('no repite la respuesta a quien acaba de darla', async () => {
    mockedPost.mockResolvedValue({
      passed: true,
      feedback: 'Eso es.',
      correct_answer: { blanks: ['fotosintesis'], explanation: 'La hoja convierte luz.' },
      show_worked_solution: false,
    })
    renderQuiz({ itemType: 'fill_blank' })

    await respondeTexto('fotosintesis')

    await waitFor(() => expect(screen.getByText('Correcto')).toBeTruthy())
    expect(screen.queryByText(SOLUTION_TITLE)).toBeNull()
    expect(screen.queryByText(NO_SOLUTION)).toBeNull()
  })
})

describe('QuizItemBlock: cerrado sin nada que enseñar', () => {
  it('lo dice en vez de callarse cuando la clave es una rubrica', async () => {
    mockedPost.mockResolvedValue({
      passed: false,
      feedback: 'Se acabaron los intentos.',
      correct_answer: null,
      show_worked_solution: true,
    })
    renderQuiz({ itemType: 'practical_case' })

    await respondeTexto('lo intento')

    await waitFor(() => expect(screen.getByText(NO_SOLUTION)).toBeTruthy())
    // Y no promete una solucion que no existe.
    expect(screen.queryByText(SOLUTION_TITLE)).toBeNull()
  })

  it('enseña la explicacion cuando el generador si la escribio', async () => {
    mockedPost.mockResolvedValue({
      passed: false,
      feedback: 'Se acabaron los intentos.',
      correct_answer: { explanation: 'Se pide el permiso antes de tocar el equipo.' },
      show_worked_solution: true,
    })
    renderQuiz({ itemType: 'practical_case' })

    await respondeTexto('lo intento')

    await waitFor(() =>
      expect(screen.getByText('Se pide el permiso antes de tocar el equipo.')).toBeTruthy(),
    )
    expect(screen.queryByText(NO_SOLUTION)).toBeNull()
  })

  /**
   * `order_steps` es el caso que hoy NO se puede arreglar desde aqui: la clave son
   * INDICES y los textos que numeran viven en `props.steps`, que no cruza el kit (ver
   * `QuizItemBlockProps.steps`). Mientras no cruce, el item cierra sin solucion — y eso
   * se dice, que es la diferencia con el panel vacio de antes.
   */
  it('no imprime un panel vacio cuando los pasos no llegan', async () => {
    mockedPost.mockResolvedValue({
      passed: false,
      feedback: 'Se acabaron los intentos.',
      correct_answer: { correct_order: [2, 0, 1] },
      show_worked_solution: true,
    })
    renderQuiz({ itemType: 'order_steps' })

    await respondeTexto('1, 2, 3')

    await waitFor(() => expect(screen.getByText(NO_SOLUTION)).toBeTruthy())
    expect(screen.queryByText(SOLUTION_TITLE)).toBeNull()
  })
})
