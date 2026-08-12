import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DidactActivityBlock } from './DidactActivityBlock'

afterEach(() => vi.restoreAllMocks())

function renderActivity(componentId = 'didact.timeline-steps') {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <DidactActivityBlock activityId="activity-1" componentId={componentId} />
    </QueryClientProvider>,
  )
}

describe('DidactActivityBlock', () => {
  it('loads a reviewed public definition and mounts an accessible component', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
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

  it('keeps locally self-grading quiz variants blocked even with the HTTP evaluation endpoint', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      activity_id: 'activity-1', component_id: 'didact.quiz.single-choice', family: 'assessment', schema_version: 1,
      public_definition: { question: 'Elige', options: [{ value: 'a', label: 'A' }] },
      required_ports: ['evaluation'], provenance: {}, status: 'ready', decline_reason: null,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

    renderActivity('didact.quiz.single-choice')
    expect(await screen.findByText('Esta actividad no está disponible en este entorno.'))
      .toHaveAttribute('data-didact-status', 'blocked')
    expect(screen.queryByText('Elige')).not.toBeInTheDocument()
  })
})
