import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LearningExperience } from './LearningExperience'

afterEach(() => vi.restoreAllMocks())

function renderExperience(props?: Partial<React.ComponentProps<typeof LearningExperience>>) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <LearningExperience
        experienceId="experience-1"
        implementationRef="didact.timeline-steps@1"
        definitionRef="activity-1"
        {...props}
      />
    </QueryClientProvider>,
  )
}

describe('LearningExperience', () => {
  it('loads the Didact adapter through a neutral, versioned reference', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      activity_id: 'activity-1',
      component_id: 'didact.timeline-steps',
      family: 'artifact',
      schema_version: 1,
      public_definition: { label: 'Proceso', steps: [{ id: 'one', title: 'Primer paso' }] },
      required_ports: [],
      provenance: {},
      status: 'ready',
      decline_reason: null,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

    renderExperience()

    expect(screen.getByRole('status')).toHaveTextContent('Cargando experiencia')
    expect(await screen.findByText('Primer paso', {}, { timeout: 5_000 })).toBeInTheDocument()
  })

  it('submits neutral Didact evaluation with its fixed binding and definition refs', async () => {
    const requests: Array<{ url: string; body?: unknown }> = []
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      requests.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined })
      if (url.endsWith('/definition')) {
        return new Response(JSON.stringify({
          activity_id: 'definition-id',
          component_id: 'didact.quiz.single-choice',
          family: 'assessment',
          schema_version: 1,
          public_definition: {
            question: 'Elige la opción segura',
            options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }],
          },
          required_ports: ['evaluation'],
          provenance: {},
          status: 'ready',
          decline_reason: null,
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      if (url.endsWith('/attempts')) {
        return new Response(JSON.stringify({
          outcome: 'correct',
          score: 1,
          result: { feedback: 'Bien' },
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      return new Response(null, { status: 204 })
    })

    renderExperience({
      experienceId: 'binding-id',
      definitionRef: 'definition-id',
      implementationRef: 'didact.quiz.single-choice@1',
    })
    await userEvent.click(await screen.findByLabelText('A'))
    await userEvent.click(screen.getByRole('button', { name: 'Comprobar respuesta' }))
    expect(await screen.findByText('Respuesta correcta.')).toBeInTheDocument()

    const attempt = requests.find((request) => request.url.endsWith('/attempts'))
    expect(attempt?.url).toBe('/api/v1/activities/definition-id/attempts')
    expect(attempt?.body).toMatchObject({
      binding_id: 'binding-id',
      submission: { answer: 'a' },
    })
    expect(requests.some((request) => request.url.endsWith('/evaluate'))).toBe(false)
  })

  it('evaluates an authored activity directly when it has no separate binding', async () => {
    const requests: Array<{ url: string; body?: unknown }> = []
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      requests.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined })
      if (url.endsWith('/definition')) {
        return new Response(JSON.stringify({
          activity_id: 'activity-1',
          component_id: 'didact.sort',
          family: 'assessment',
          schema_version: 1,
          public_definition: {
            title: 'Ordena el procedimiento',
            items: [{ id: 'step-1', content: 'Primero' }, { id: 'step-2', content: 'Después' }],
          },
          required_ports: ['evaluation'],
          provenance: {},
          status: 'ready',
          decline_reason: null,
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      if (url.endsWith('/evaluate')) {
        return new Response(JSON.stringify({
          status: 'completed',
          result: { outcome: 'correct', passed: true, score: 1, feedback: null },
          decline_reason: null,
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      return new Response(null, { status: 204 })
    })

    // Authored activity: the runtime reuses the activity id for both neutral refs.
    renderExperience({
      experienceId: 'activity-1',
      definitionRef: 'activity-1',
      implementationRef: 'didact.sort@1',
    })
    await userEvent.click(await screen.findByRole('button', { name: 'Comprobar respuesta' }))
    expect(await screen.findByText('Respuesta correcta.')).toBeInTheDocument()

    const evaluate = requests.find((request) => request.url.endsWith('/evaluate'))
    expect(evaluate?.url).toBe('/api/v1/activities/activity-1/evaluate')
    expect(evaluate?.body).toMatchObject({ submission: { answer: ['step-1', 'step-2'] } })
    expect(requests.some((request) => request.url.endsWith('/attempts'))).toBe(false)
  })

  it('announces an unavailable implementation without attempting a network request', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch')
    renderExperience({ implementationRef: 'video.checkpoint@1' })

    expect(await screen.findByRole('alert')).toHaveTextContent('no está disponible')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('rejects incomplete neutral references accessibly', () => {
    renderExperience({ experienceId: '' })

    expect(screen.getByRole('alert')).toHaveTextContent('no es válida')
  })

  it('loads a second provider without involving the Didact API or the central renderer', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch')
    const view = renderExperience({
      implementationRef: 'media.checkpoint-video@1',
      definitionRef: 'definition-video-1@1',
      publicDefinition: {
        src: '/assets/training/checkpoint.mp4',
        title: 'Manipulación segura',
        captionsSrc: '/assets/training/checkpoint.es.vtt',
        transcript: 'Primero, separa los utensilios.',
        checkpointText: '¿Qué riesgo evita esta separación?',
      },
    })

    const video = await screen.findByLabelText('Manipulación segura')
    expect(video).toHaveAttribute('controls')
    expect(video).not.toHaveAttribute('autoplay')
    expect(video).toHaveAttribute('preload', 'metadata')
    expect(view.container.querySelector('track[kind="captions"]')).toHaveAttribute(
      'src',
      '/assets/training/checkpoint.es.vtt',
    )
    expect(screen.getByText('Primero, separa los utensilios.')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Punto de comprobación' }))
      .toHaveTextContent('¿Qué riesgo evita esta separación?')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('rejects unsafe or inaccessible video definitions', async () => {
    renderExperience({
      implementationRef: 'media.checkpoint-video@1',
      definitionRef: 'definition-video-unsafe@1',
      publicDefinition: { src: 'javascript:alert(1)', title: 'Unsafe' },
    })

    expect(await screen.findByRole('alert')).toHaveTextContent('subtítulos o transcripción')
    expect(document.querySelector('video')).not.toBeInTheDocument()
  })

  it('renders the minimal SkillNet text fallback from a resolved public definition', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch')
    renderExperience({
      implementationRef: 'skillnet.text-content@1',
      definitionRef: 'definition-text-1@1',
      publicDefinition: {
        content: 'Revisa la regla antes de decidir.',
        variant: 'lead',
      },
    })

    const content = await screen.findByRole('group', { name: /Texto explorable/ })
    expect(content).toHaveTextContent('Revisa la regla antes de decidir.')
    expect(content).toHaveClass('text-lesson-lead')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('announces an invalid text fallback instead of rendering arbitrary content', async () => {
    renderExperience({
      implementationRef: 'skillnet.text-content@1',
      definitionRef: 'definition-text-invalid@1',
      publicDefinition: { content: '', variant: 'lead' },
    })

    expect(await screen.findByRole('alert')).toHaveTextContent('no es válido')
  })
})
