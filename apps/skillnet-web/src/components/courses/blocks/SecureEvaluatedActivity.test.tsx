import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import type { DidactHostPorts, EvaluationResult } from '../../../lib/didact'
import { SecureEvaluatedActivity } from './SecureEvaluatedActivity'

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
