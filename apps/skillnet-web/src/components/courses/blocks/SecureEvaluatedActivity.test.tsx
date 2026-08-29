import { render as rtlRender, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactElement } from 'react'

import { ActivityNotEvaluableError } from '../../../lib/didact'
import type { DidactHostPorts, EvaluationResult } from '../../../lib/didact'
import { es } from '../../../i18n/es'
import { SecureEvaluatedActivity } from './SecureEvaluatedActivity'
import { lessonFeedbackContext, stepperSolveContext } from './StepperContext'

// The hint ladder and the "see the solution" button are the two things here that talk to
// the server directly (everything else goes through the injected ports), so the transport
// is replaced and `ApiError` is kept real — `HintLadder` prints a 409 by instance check.
vi.mock('../../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../../api/client')>('../../../api/client')
  return { ...actual, get: vi.fn(), post: vi.fn(), put: vi.fn() }
})

import { ApiError, post } from '../../../api/client'

const mockedPost = vi.mocked(post)

beforeEach(() => {
  mockedPost.mockReset()
})

/** Everything under test needs a query client: `HintLadder` and the solution both mutate. */
function render(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

/** Ports whose grader returns a scripted outcome per attempt, and records what it saw. */
function scriptedPorts(outcomes: EvaluationResult[]) {
  const attemptIds: string[] = []
  const submissions: unknown[] = []
  let attempt = 0
  const ports: DidactHostPorts = {
    events: { async emit() {} },
    evaluation: {
      async evaluate({ attemptId, response }) {
        attemptIds.push(String(attemptId))
        submissions.push((response as { answer?: unknown } | undefined)?.answer)
        const outcome = outcomes[Math.min(attempt, outcomes.length - 1)]
        attempt += 1
        return outcome
      },
    },
  }
  return { ports, attemptIds, submissions }
}

function renderChoice(outcomes: EvaluationResult[]) {
  const scripted = scriptedPorts(outcomes)
  render(
    <SecureEvaluatedActivity
      activityId="activity-1"
      componentId="didact.quiz.single-choice"
      componentProps={{
        question: '¿Cuándo se revisa el registro?',
        options: [
          { value: 'a', label: 'Cada semana' },
          { value: 'b', label: 'Cada mes' },
        ],
      }}
      ports={scripted.ports}
    />,
  )
  return scripted
}

describe('SecureEvaluatedActivity retries', () => {
  it('reports a wrong answer as wrong and offers another attempt', async () => {
    const user = userEvent.setup()
    renderChoice([{ outcome: 'incorrect', score: 0 }])

    await user.click(screen.getByLabelText('Cada semana'))
    await user.click(screen.getByRole('button', { name: 'Comprobar respuesta' }))

    expect(await screen.findByText('La respuesta no es correcta. Vuelve a intentarlo.')).toBeInTheDocument()
    expect(screen.queryByText(/necesita revisión/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
  })

  it('re-enables and clears the controls after a retry, and scores the new attempt', async () => {
    const user = userEvent.setup()
    const scripted = renderChoice([{ outcome: 'incorrect', score: 0 }, { outcome: 'correct', score: 1 }])

    await user.click(screen.getByLabelText('Cada semana'))
    await user.click(screen.getByRole('button', { name: 'Comprobar respuesta' }))
    expect(await screen.findByRole('button', { name: 'Reintentar' })).toBeEnabled()
    expect(screen.getByLabelText('Cada semana')).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Reintentar' }))

    const firstOption = screen.getByLabelText('Cada semana')
    expect(firstOption).toBeEnabled()
    expect(firstOption).not.toBeChecked()
    expect(screen.getByLabelText('Cada mes')).not.toBeChecked()
    expect(screen.queryByText('La respuesta no es correcta. Vuelve a intentarlo.')).not.toBeInTheDocument()
    // The submit button is back, and disabled until the new attempt has an answer.
    expect(screen.getByRole('button', { name: 'Comprobar respuesta' })).toBeDisabled()

    await user.click(screen.getByLabelText('Cada mes'))
    await user.click(screen.getByRole('button', { name: 'Comprobar respuesta' }))

    expect(await screen.findByText('Respuesta correcta.')).toBeInTheDocument()
    // Each submission is its own server attempt, with its own id.
    expect(scripted.attemptIds).toHaveLength(2)
    expect(new Set(scripted.attemptIds).size).toBe(2)
    expect(scripted.submissions).toEqual(['a', 'b'])
  })

  it('does not offer a retry once the answer is correct', async () => {
    const user = userEvent.setup()
    renderChoice([{ outcome: 'correct', score: 1 }])

    await user.click(screen.getByLabelText('Cada mes'))
    await user.click(screen.getByRole('button', { name: 'Comprobar respuesta' }))

    expect(await screen.findByText('Respuesta correcta.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reintentar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Comprobar respuesta' })).not.toBeInTheDocument()
  })

  it('restores the starting order of a sort activity on retry', async () => {
    const user = userEvent.setup()
    const scripted = scriptedPorts([{ outcome: 'incorrect', score: 0 }, { outcome: 'correct', score: 1 }])
    render(
      <SecureEvaluatedActivity
        activityId="activity-2"
        componentId="didact.sort"
        componentProps={{
          title: 'Ordena los pasos',
          items: [
            { id: 'one', content: 'Primero' },
            { id: 'two', content: 'Segundo' },
          ],
        }}
        ports={scripted.ports}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Bajar Primero' }))
    await user.click(screen.getByRole('button', { name: 'Comprobar respuesta' }))
    expect(await screen.findByText('La respuesta no es correcta. Vuelve a intentarlo.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(screen.getByRole('button', { name: 'Subir Primero' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Bajar Primero' })).toBeEnabled()

    await user.click(screen.getByRole('button', { name: 'Comprobar respuesta' }))
    expect(await screen.findByText('Respuesta correcta.')).toBeInTheDocument()
    expect(scripted.submissions).toEqual([['two', 'one'], ['one', 'two']])
  })
})

describe('SecureEvaluatedActivity fill-in-the-blank', () => {
  function renderBlank(question: string) {
    const scripted = scriptedPorts([{ outcome: 'incorrect', score: 0 }])
    render(
      <SecureEvaluatedActivity
        activityId="activity-3"
        componentId="didact.quiz.fill-in-the-blank"
        componentProps={{ question }}
        ports={scripted.ports}
      />,
    )
    return scripted
  }

  it('shows the sentence with the gap in the position the author wrote it', async () => {
    const user = userEvent.setup()
    const scripted = renderBlank('El alérgeno se declara siempre al ____ que lo pregunta.')

    expect(screen.getByText('El alérgeno se declara siempre al')).toBeInTheDocument()
    expect(screen.getByText('que lo pregunta.')).toBeInTheDocument()
    const gap = screen.getByLabelText('Palabra que falta')

    await user.type(gap, 'cliente')
    await user.click(screen.getByRole('button', { name: 'Comprobar respuesta' }))

    expect(await screen.findByText('La respuesta no es correcta. Vuelve a intentarlo.')).toBeInTheDocument()
    expect(scripted.submissions).toEqual(['cliente'])
    await user.click(screen.getByRole('button', { name: 'Reintentar' }))
    expect(screen.getByLabelText('Palabra que falta')).toHaveValue('')
  })

  it('labels the field when the sentence carries no written gap', () => {
    renderBlank('Completa la frase con el término de la fuente.')

    expect(screen.getByText('Completa la frase con el término de la fuente.')).toBeInTheDocument()
    expect(screen.getByLabelText('Palabra que falta')).toBeInTheDocument()
  })
})

/**
 * The way out of the dead end.
 *
 * Until 2026-08-28 this component knew one sentence, "try again": whoever could not sort
 * five items stayed there forever — and now that the step holding it is born closed
 * (`kit/solvableSteps.ts`), "forever" would be literal. These exits are what prevents it.
 *
 * Every signal comes from the server; the client decides none of them. The doubles below
 * write down the contract: `show_worked_solution` plus a `solution` already written out.
 */
describe('SecureEvaluatedActivity when the attempts run out', () => {
  function renderWithStepper(outcomes: EvaluationResult[] | Error) {
    const solve = vi.fn()
    const report = vi.fn()
    const scripted = outcomes instanceof Error
      ? {
          ports: {
            events: { async emit() {} },
            evaluation: {
              async evaluate() {
                throw outcomes
              },
            },
          } satisfies DidactHostPorts,
        }
      : scriptedPorts(outcomes)
    render(
      <stepperSolveContext.Provider value={solve}>
        <lessonFeedbackContext.Provider value={{ report }}>
          <SecureEvaluatedActivity
            activityId="activity-4"
            componentId="didact.quiz.single-choice"
            componentProps={{
              question: '¿Cuándo se revisa el registro?',
              options: [
                { value: 'a', label: 'Cada semana' },
                { value: 'b', label: 'Cada mes' },
              ],
            }}
            ports={scripted.ports}
          />
        </lessonFeedbackContext.Provider>
      </stepperSolveContext.Provider>,
    )
    return { solve, report }
  }

  async function answer(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByLabelText('Cada semana'))
    await user.click(screen.getByRole('button', { name: 'Comprobar respuesta' }))
  }

  it('prints the solution the server wrote and closes the item', async () => {
    const user = userEvent.setup()
    const { solve, report } = renderWithStepper([
      {
        outcome: 'incorrect',
        score: 0,
        showWorkedSolution: true,
        solution: {
          solution: 'El primer lunes de cada mes',
          explanation: 'El ciclo de revisión es mensual.',
        },
      },
    ])

    await answer(user)

    expect(await screen.findByText('Solución paso a paso')).toBeInTheDocument()
    expect(screen.getByText('El primer lunes de cada mes')).toBeInTheDocument()
    expect(screen.getByText('El ciclo de revisión es mensual.')).toBeInTheDocument()
    expect(screen.getByText('Esta actividad queda cerrada. Ya puedes seguir con la lección.')).toBeInTheDocument()
    // Closed: no retry, and no promise of one in the result copy either.
    expect(screen.queryByRole('button', { name: 'Reintentar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Comprobar respuesta' })).not.toBeInTheDocument()
    expect(screen.getByText('La respuesta no es correcta. Aquí tienes la solución.')).toBeInTheDocument()
    // And above all: the step opens. Without this the learner has the solution in front
    // of them and still cannot move on.
    expect(solve).toHaveBeenCalled()
    expect(report).toHaveBeenCalledWith('fallo', { definitivo: true })
  })

  it('is honest when the item closes with no solution to show', async () => {
    // `show_worked_solution: true` with `solution: null` is a real server answer:
    // `render_solution` returns `None` for an evaluation mode it cannot write out. The
    // panel then prints nothing, so "aquí tienes la solución" promised something that
    // never arrived — and with the item closed there was no retry either, leaving the
    // learner in front of a blank promise.
    const user = userEvent.setup()
    const { solve } = renderWithStepper([
      { outcome: 'incorrect', score: 0, showWorkedSolution: true, solution: null },
    ])

    await answer(user)

    expect(
      await screen.findByText(/No podemos mostrarte la solución de esta actividad/),
    ).toBeInTheDocument()
    expect(screen.queryByText('La respuesta no es correcta. Aquí tienes la solución.')).not.toBeInTheDocument()
    // No empty panel under the sentence either.
    expect(screen.queryByText('Solución paso a paso')).not.toBeInTheDocument()
    // The item is still closed, and the step still opens: the way out does not depend on
    // the solution being printable.
    expect(screen.queryByRole('button', { name: 'Reintentar' })).not.toBeInTheDocument()
    expect(solve).toHaveBeenCalled()
  })

  it('keeps offering a retry until the server closes the item', async () => {
    const user = userEvent.setup()
    const { solve, report } = renderWithStepper([{ outcome: 'incorrect', score: 0 }])

    await answer(user)

    expect(await screen.findByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
    expect(screen.queryByText('Solución paso a paso')).not.toBeInTheDocument()
    expect(solve).not.toHaveBeenCalled()
    expect(report).toHaveBeenCalledWith('fallo')
  })

  it('opens the step on a correct answer, just like the quiz', async () => {
    const user = userEvent.setup()
    const { solve, report } = renderWithStepper([{ outcome: 'correct', score: 1 }])

    await answer(user)

    expect(await screen.findByText('Respuesta correcta.')).toBeInTheDocument()
    expect(solve).toHaveBeenCalled()
    expect(report).toHaveBeenCalledWith('acierto')
  })

  it('does not ask for a retry on an activity that cannot be graded: it says so and lets the learner out', async () => {
    const user = userEvent.setup()
    const { solve } = renderWithStepper(new ActivityNotEvaluableError('activity cannot be evaluated: no key'))

    await answer(user)

    expect(
      await screen.findByText(/Esta actividad no se puede corregir/),
    ).toBeInTheDocument()
    // The "try again" line is for a transient failure, not for this.
    expect(screen.queryByText(/No se pudo evaluar la respuesta/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reintentar' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Comprobar respuesta' })).not.toBeInTheDocument()
    // Immediately, not after four attempts.
    expect(solve).toHaveBeenCalled()
  })

  it('leaves a network failure retryable, and does not open the step', async () => {
    const user = userEvent.setup()
    const { solve } = renderWithStepper(new Error('network'))

    await answer(user)

    expect(await screen.findByText(/No se pudo evaluar la respuesta/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Comprobar respuesta' })).toBeInTheDocument()
    expect(solve).not.toHaveBeenCalled()
  })
})

/**
 * The activity that cannot even be painted.
 *
 * The step was closed by reading the program, before anyone knew the definition was
 * unusable. Without this exit the learner would be locked in by an error box.
 */
describe('SecureEvaluatedActivity without a valid public definition', () => {
  it('opens the step as soon as it mounts', () => {
    const solve = vi.fn()
    const scripted = scriptedPorts([{ outcome: 'correct', score: 1 }])
    render(
      <stepperSolveContext.Provider value={solve}>
        <SecureEvaluatedActivity
          activityId="activity-5"
          componentId="didact.quiz.single-choice"
          componentProps={{}}
          ports={scripted.ports}
        />
      </stepperSolveContext.Provider>,
    )

    expect(screen.getByText('La actividad no tiene una definición pública válida.')).toBeInTheDocument()
    expect(solve).toHaveBeenCalled()
  })
})

/**
 * The two exits the learner can take on purpose.
 *
 * Until now the only way out of a Didact activity was to fail it four times and be handed
 * the solution — help you get by running out, not by asking. The owner asked for both
 * buttons, and both talk to endpoints that do not exist yet, so the doubles below are the
 * contract: `POST /activities/{id}/hint` answers in the shape `/nodes/{id}/hint` already
 * answers in (which is why one `HintLadder` serves both), and
 * `POST /activities/{id}/solution` answers in the shape `result.solution` already arrives
 * in — including the shape where there is nothing to say.
 */
describe('SecureEvaluatedActivity — asking for help', () => {
  function renderActivity() {
    const solve = vi.fn()
    const report = vi.fn()
    const scripted = scriptedPorts([{ outcome: 'incorrect', score: 0 }])
    render(
      <stepperSolveContext.Provider value={solve}>
        <lessonFeedbackContext.Provider value={{ report }}>
          <SecureEvaluatedActivity
            activityId="activity-6"
            componentId="didact.quiz.single-choice"
            componentProps={{
              question: '¿Cuándo se revisa el registro?',
              options: [
                { value: 'a', label: 'Cada semana' },
                { value: 'b', label: 'Cada mes' },
              ],
            }}
            ports={scripted.ports}
          />
        </lessonFeedbackContext.Provider>
      </stepperSolveContext.Provider>,
    )
    return { solve, report }
  }

  const hintButton = () => screen.getByRole('button', { name: es['hints.request'] })
  const revealButton = () => screen.getByRole('button', { name: es['hints.reveal'] })

  it('asks the activity endpoint for a hint and prints what the server sent', async () => {
    const user = userEvent.setup()
    mockedPost.mockResolvedValue({ hint: 'Mira la fecha del último cierre', hints_used: 1, hints_remaining: 2 })
    renderActivity()

    await user.click(hintButton())

    expect(await screen.findByText('Mira la fecha del último cierre')).toBeInTheDocument()
    expect(mockedPost).toHaveBeenCalledWith('/activities/activity-6/hint', {})
    // The count on screen is the server's, never a tally of clicks.
    expect(screen.getByText('Pista 1 de 3')).toBeInTheDocument()
  })

  it('prints the server refusal verbatim instead of a rule of its own', async () => {
    const user = userEvent.setup()
    mockedPost.mockRejectedValue(new ApiError(409, { detail: 'Inténtalo una vez antes de pedir una pista.' }))
    renderActivity()

    await user.click(hintButton())

    expect(await screen.findByText('Inténtalo una vez antes de pedir una pista.')).toBeInTheDocument()
  })

  it('shows the solution when the learner asks for it, and opens the step', async () => {
    const user = userEvent.setup()
    mockedPost.mockResolvedValue({ solution: 'El primer lunes de cada mes', explanation: 'El ciclo es mensual.' })
    const { solve, report } = renderActivity()

    await user.click(revealButton())

    expect(await screen.findByText('El primer lunes de cada mes')).toBeInTheDocument()
    expect(screen.getByText('El ciclo es mensual.')).toBeInTheDocument()
    expect(mockedPost).toHaveBeenCalledWith('/activities/activity-6/solution', {})
    // Closed: nothing left to answer, nothing left to ask for.
    expect(screen.queryByRole('button', { name: 'Comprobar respuesta' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: es['hints.reveal'] })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: es['hints.request'] })).not.toBeInTheDocument()
    // And the step opens, or the learner reads the answer and stays shut in.
    expect(solve).toHaveBeenCalled()
    // Asking for help is not a verdict: no red, no mascot.
    expect(report).not.toHaveBeenCalled()
  })

  it('is honest when the server has no solution written for the activity', async () => {
    const user = userEvent.setup()
    // The same answer `render_solution` gives for an evaluation mode it cannot put into
    // words. It still closes the activity, so the learner still has to be let out.
    mockedPost.mockResolvedValue(null)
    const { solve } = renderActivity()

    await user.click(revealButton())

    expect(await screen.findByText(es['activity.solutionUnavailable'])).toBeInTheDocument()
    expect(screen.queryByText('Solución paso a paso')).not.toBeInTheDocument()
    expect(solve).toHaveBeenCalled()
  })

  it('leaves the activity open when the solution request fails', async () => {
    const user = userEvent.setup()
    mockedPost.mockRejectedValue(new Error('network'))
    const { solve } = renderActivity()

    await user.click(revealButton())

    expect(await screen.findByText(es['hints.revealError'])).toBeInTheDocument()
    // A failed request is not a solution: nothing closed, nothing opened.
    expect(screen.getByRole('button', { name: 'Comprobar respuesta' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: es['hints.reveal'] })).toBeInTheDocument()
    expect(solve).not.toHaveBeenCalled()
  })

  it('keeps the hints already earned on screen once the activity closes', async () => {
    const user = userEvent.setup()
    mockedPost.mockResolvedValueOnce({ hint: 'Mira la fecha del último cierre', hints_used: 1, hints_remaining: 2 })
    mockedPost.mockResolvedValueOnce({ solution: 'El primer lunes de cada mes' })
    renderActivity()

    await user.click(hintButton())
    expect(await screen.findByText('Mira la fecha del último cierre')).toBeInTheDocument()

    await user.click(revealButton())

    expect(await screen.findByText('El primer lunes de cada mes')).toBeInTheDocument()
    // The hint stays next to the solution; only the way to ask for another goes away.
    expect(screen.getByText('Mira la fecha del último cierre')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: es['hints.request'] })).not.toBeInTheDocument()
  })
})
