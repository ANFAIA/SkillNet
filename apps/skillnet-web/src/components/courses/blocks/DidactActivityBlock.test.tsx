import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { DidactEventType, DidactHostPorts } from '../../../lib/didact'
import { DidactActivityBlock } from './DidactActivityBlock'
import { evaluationProps } from './didact-evaluation-adapter'

afterEach(() => vi.restoreAllMocks())

function renderActivity(componentId = 'didact.timeline-steps') {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DidactActivityBlock activityId="activity-1" componentId={componentId} />
    </QueryClientProvider>,
  )
}

describe('DidactActivityBlock', () => {
  it.each([
    ['didact.matching', { title: 'Matching', sources: [], targets: [] }],
    ['didact.sort', { title: 'Sort', items: [] }],
    ['didact.categorize', { title: 'Categorize', items: [], categories: [] }],
    ['didact.quiz.single-choice', { question: 'Single choice', options: [] }],
    ['didact.quiz.multi-select', { question: 'Multi select', options: [] }],
    ['didact.quiz.true-false', { question: 'True or false' }],
    ['didact.quiz.fill-in-the-blank', { question: 'Fill blank' }],
    ['didact.quiz.short-answer', { question: 'Short answer' }],
    ['didact.completion-problem', { problem: 'Completion', steps: [] }],
    ['didact.numeric-question', { prompt: 'Numeric' }],
    ['didact.word-bank', { title: 'Word bank', gaps: [], options: [] }],
  ])('mounts the secure server-evaluated adapter for %s', async (componentId, publicDefinition) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      activity_id: 'activity-1',
      component_id: componentId,
      family: 'assessment',
      schema_version: 1,
      public_definition: publicDefinition,
      required_ports: ['evaluation'],
      provenance: {},
      status: 'ready',
      decline_reason: null,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

    const view = renderActivity(componentId)
    expect(await view.findByText(Object.values(publicDefinition)[0] as string)).toBeInTheDocument()
    expect(view.container.querySelector('[data-didact-secure-adapter]')).toHaveAttribute(
      'data-didact-secure-adapter',
      componentId,
    )
    view.unmount()
  })

  it('emits completion after an evaluated response without claiming mastery', async () => {
    const observed: DidactEventType[] = []
    const ports: DidactHostPorts = {
      events: {
        async emit(event) {
          observed.push(event.type)
        },
      },
      evaluation: {
        async evaluate() {
          return { outcome: 'incorrect', score: 0, feedback: 'Inténtalo de nuevo' }
        },
      },
    }
    const props = evaluationProps('activity-1', 'didact.measurement-lab', ports)

    await (props.evaluate as (state: unknown) => Promise<unknown>)({ value: 42 })

    expect(observed).toEqual(['attempted', 'answered', 'completed'])
    expect(observed).not.toContain('mastered')
  })

  it('loads a reviewed public definition and mounts an accessible component', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      activity_id: 'activity-1',
      component_id: 'didact.timeline-steps',
      family: 'artifact',
      schema_version: 1,
      public_definition: { label: 'Proceso', steps: [{ id: 'one', title: 'Primer paso' }] },
      required_ports: [], provenance: {}, status: 'ready', decline_reason: null,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

    renderActivity()
    expect(screen.getByText('Cargando actividad…')).toHaveAttribute('role', 'status')
    expect(await screen.findByText('Primer paso')).toBeInTheDocument()
    await waitFor(() => {
      expect(fetch.mock.calls.some(([url]) => String(url).endsWith('/activities/activity-1/events'))).toBe(true)
    })
    const eventRequest = fetch.mock.calls.find(([url]) => String(url).endsWith('/events'))?.[1]
    expect(JSON.parse(String(eventRequest?.body))).toMatchObject({
      version: 1,
      activity_id: 'activity-1',
      component_id: 'didact.timeline-steps',
      type: 'started',
      payload: {},
    })
  })

  it('does not mount a mismatched server definition', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      activity_id: 'activity-1', component_id: 'didact.flashcard', family: 'artifact', schema_version: 1,
      public_definition: { front: 'Secret prompt', back: 'Secret answer' }, required_ports: [],
      provenance: {}, status: 'ready', decline_reason: null,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

    renderActivity('didact.code-exercise')
    expect(await screen.findByRole('alert')).toHaveTextContent('no es válida')
    expect(screen.queryByText('Secret answer')).not.toBeInTheDocument()
  })

  it('announces declined activities as blocked, not as completed', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      activity_id: 'activity-1', component_id: 'didact.simulation-lab', family: 'simulation', schema_version: 1,
      public_definition: {}, required_ports: ['simulation'], provenance: {}, status: 'declined',
      decline_reason: 'missing source model',
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

    renderActivity('didact.simulation-lab')
    expect(await screen.findByText('Esta actividad no puede ejecutarse con los datos disponibles.'))
      .toHaveAttribute('data-didact-activity-status', 'blocked')
  })

  it('evaluates a quiz through the server adapter without an answer key in props, DOM or events', async () => {
    const requests: Array<{ url: string; body?: unknown }> = []
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      requests.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined })
      if (url.endsWith('/definition')) {
        return new Response(JSON.stringify({
          activity_id: 'activity-1', component_id: 'didact.quiz.single-choice', family: 'assessment', schema_version: 1,
          public_definition: {
            question: 'Elige',
            options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }],
            nested: { answerKey: 'must be stripped' },
          },
          required_ports: ['evaluation'], provenance: {}, status: 'ready', decline_reason: null,
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      if (url.endsWith('/evaluate')) {
        return new Response(JSON.stringify({
          status: 'completed',
          result: { outcome: 'correct', score: 1, feedback: 'Bien' },
          decline_reason: null,
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      return new Response(null, { status: 204 })
    })

    renderActivity('didact.quiz.single-choice')
    expect(await screen.findByText('Elige')).toBeInTheDocument()
    expect(document.body.innerHTML).not.toContain('must be stripped')
    await userEvent.click(screen.getByLabelText('A'))
    await userEvent.click(screen.getByRole('button', { name: 'Comprobar respuesta' }))
    expect(await screen.findByText('Respuesta correcta.')).toBeInTheDocument()

    const evaluation = requests.find((request) => request.url.endsWith('/evaluate'))
    expect(evaluation?.body).toEqual({ submission: { answer: 'a' } })
    const eventBodies = requests
      .filter((request) => request.url.endsWith('/events'))
      .map((request) => JSON.stringify(request.body))
    expect(eventBodies.join('')).not.toMatch(/"answer"|"a"/)
  })
})
