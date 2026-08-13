import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Onboarding } from './Onboarding'
import type { OnboardingRead } from '../../api/onboarding'

/**
 * One question per screen, skippable at any moment, and
 * skipping declares **nothing** — the server writes `experience_level = 'unknown'`,
 * and `'none'` never leaves this wizard unless the learner picked "Ninguna".
 */

let reduceMotion = false

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual<typeof import('framer-motion')>('framer-motion')
  return { ...actual, useReducedMotion: () => reduceMotion }
})

const mockFetch = vi.fn()

const QUESTIONS: OnboardingRead = {
  version: 1,
  completed: false,
  notice:
    'Tu puesto y tu sector se envían al proveedor de IA para adaptar los ejemplos. Puedes borrarlos cuando quieras desde Ajustes.',
  questions: [
    {
      id: 'role_title',
      kind: 'text_suggest',
      prompt: '¿Cuál es tu puesto?',
      suggestions: ['Dependiente', 'Cajero', 'Encargado de turno', 'Reponedor', 'Responsable de tienda', 'Atención al cliente'],
    },
    {
      id: 'goal',
      kind: 'single_choice',
      prompt: '¿Para qué quieres usar SkillNet ahora mismo?',
      options: [
        { value: 'onboarding', label: 'Acabo de entrar y quiero ponerme al día' },
        { value: 'specific_gap', label: 'Hay algo concreto que necesito dominar' },
        { value: 'assigned', label: 'Me han asignado formación' },
      ],
      allow_other: true,
    },
    {
      id: 'experience_level',
      kind: 'single_choice',
      prompt: '¿Cuánta experiencia tienes en tu puesto actual?',
      options: [
        { value: 'none', label: 'Ninguna' },
        { value: 'some', label: 'Algo' },
        { value: 'experienced', label: 'Bastante' },
      ],
    },
    {
      id: 'preset',
      kind: 'single_choice',
      prompt: '¿Cómo prefieres estudiar?',
      options: [
        { value: 'standard', label: 'Estándar', hint: 'Bloques de 10-15 min' },
        { value: 'focus', label: 'Concentración', hint: 'Paso a paso, sin distracciones' },
        { value: 'fast', label: 'Ritmo rápido', hint: 'Micro-bloques de 3-5 min' },
      ],
    },
    {
      id: 'learning_preferences',
      kind: 'single_choice',
      prompt: '¿Qué formato te ayuda a empezar?',
      optional: true,
      options: [
        { value: 'balanced', label: 'Una mezcla equilibrada' },
        { value: 'visual', label: 'Verlo de forma visual' },
        { value: 'text', label: 'Leer una explicación clara' },
        { value: 'audio', label: 'Escucharlo' },
        { value: 'data', label: 'Ver los datos' },
      ],
    },
    {
      id: 'accessibility',
      kind: 'multi_choice',
      optional: true,
      prompt: '¿Quieres activar algún ajuste de lectura?',
      options: [
        { value: 'short_blocks', label: 'Bloques más cortos' },
        { value: 'reduce_motion', label: 'Menos animaciones' },
        { value: 'high_contrast', label: 'Más contraste' },
        { value: 'extra_time', label: 'Sin límite de tiempo' },
      ],
    },
  ],
}

const PROFILE = {
  role_title: 'Cajero',
  sector: 'retail',
  goal: 'assigned',
  experience_level: 'experienced',
  preset: 'focus',
  nodes_completed: 0,
  onboarding_completed_at: '2026-07-25T09:12:00Z',
  onboarding_skipped: false,
  calibrating: true,
}

function json(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  })
}

function serve(options: { questionsStatus?: number } = {}) {
  mockFetch.mockImplementation((url: string) => {
    const path = String(url).replace('/api/v1', '')
    if (path === '/health') {
      return json({ status: 'ok', version: '0.1.0', database: 'connected' })
    }
    if (path === '/onboarding') {
      if (options.questionsStatus && options.questionsStatus >= 400) {
        return json({ detail: 'Not Found' }, options.questionsStatus)
      }
      return json(QUESTIONS)
    }
    if (path === '/onboarding/skip') return json(PROFILE)
    return json({ detail: 'Not Found' }, 404)
  })
}

function renderWizard() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/onboarding']}>
        <Routes>
          <Route path="/onboarding" element={<Onboarding />} />
          <Route path="/empleado" element={<div>HOME</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** Bodies of every POST the wizard made, in order. */
function postBodies(path: string): unknown[] {
  return mockFetch.mock.calls
    .filter((call) => String(call[0]) === `/api/v1${path}` && (call[1] as RequestInit)?.method === 'POST')
    .map((call) => {
      const body = (call[1] as RequestInit).body
      return body === undefined ? undefined : JSON.parse(String(body))
    })
}

function currentStep(): HTMLElement {
  return document.querySelector('[data-step]') as HTMLElement
}

beforeEach(() => {
  reduceMotion = false
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
  mockFetch.mockReset()
})

describe('Onboarding — shape (§6.1)', () => {
  it('shows exactly one question at a time', async () => {
    serve()
    renderWizard()
    expect(await screen.findByText('¿Cuál es tu puesto?')).toBeInTheDocument()
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(1)
    expect(screen.queryByText('¿Cómo prefieres estudiar?')).toBeNull()
  })

  it('announces the step count as text, since the indicator only draws digits', async () => {
    serve()
    renderWizard()
    await screen.findByText('¿Cuál es tu puesto?')
    expect(screen.getByRole('status')).toHaveTextContent('Paso 1 de 6')
  })

  it('carries the art. 13 notice from the server on screen 1, at body weight (§3.3)', async () => {
    serve()
    renderWizard()
    const notice = await screen.findByText(QUESTIONS.notice)
    // Not fine print: body size, body colour.
    expect(notice.className).toContain('text-sm')
    expect(notice.className).toContain('text-text')
    expect(notice.className).not.toContain('text-xs')
  })

  it('blocks Continuar until the question is answered', async () => {
    const user = userEvent.setup()
    serve()
    renderWizard()
    await screen.findByText('¿Cuál es tu puesto?')

    expect(screen.getByRole('button', { name: 'Continuar' })).toBeDisabled()
    await user.type(screen.getByRole('textbox'), 'Cajero')
    expect(screen.getByRole('button', { name: 'Continuar' })).toBeEnabled()
  })

  it('walks the screens and submits the declared learning preference', async () => {
    const user = userEvent.setup()
    serve()
    renderWizard()

    await screen.findByText('¿Cuál es tu puesto?')
    await user.click(screen.getByRole('button', { name: 'Cajero' })) // suggestion chip
    await user.click(screen.getByRole('button', { name: 'Continuar' }))

    await screen.findByText('¿Para qué quieres usar SkillNet ahora mismo?')
    await user.click(screen.getByRole('radio', { name: 'Me han asignado formación' }))
    await user.click(screen.getByRole('button', { name: 'Continuar' }))

    await screen.findByText('¿Cuánta experiencia tienes en tu puesto actual?')
    await user.click(screen.getByRole('radio', { name: 'Bastante' }))
    await user.click(screen.getByRole('button', { name: 'Continuar' }))

    await screen.findByText('¿Cómo prefieres estudiar?')
    await user.click(screen.getByRole('radio', { name: /Concentración/ }))
    await user.click(screen.getByRole('button', { name: 'Continuar' }))

    await screen.findByText('¿Qué formato te ayuda a empezar?')
    await user.click(screen.getByRole('radio', { name: 'Verlo de forma visual' }))
    await user.click(screen.getByRole('button', { name: 'Continuar' }))

    await screen.findByText('¿Quieres activar algún ajuste de lectura?')
    await user.click(screen.getByRole('checkbox', { name: 'Bloques más cortos' }))
    await user.click(screen.getByRole('button', { name: 'Finalizar' }))

    await waitFor(() => expect(postBodies('/onboarding')).toHaveLength(1))
    expect(postBodies('/onboarding')[0]).toEqual({
      role_title: 'Cajero',
      goal: 'assigned',
      experience_level: 'experienced',
      preset: 'focus',
      learning_preferences: {
        version: 2,
        modality: 'visual',
        interaction: 'standard',
        detail: 'standard',
        images: 'when_useful',
      },
      accessibility: {
        short_blocks: true,
        reduce_motion: false,
        high_contrast: false,
        extra_time: false,
      },
    })
    expect(await screen.findByText('HOME')).toBeInTheDocument()
  })

  it('keeps the answers when stepping back', async () => {
    const user = userEvent.setup()
    serve()
    renderWizard()

    await screen.findByText('¿Cuál es tu puesto?')
    await user.type(screen.getByRole('textbox'), 'Cajero')
    await user.click(screen.getByRole('button', { name: 'Continuar' }))

    await screen.findByText('¿Para qué quieres usar SkillNet ahora mismo?')
    await user.click(screen.getByRole('button', { name: 'Atrás' }))

    await screen.findByText('¿Cuál es tu puesto?')
    expect(screen.getByRole('textbox')).toHaveValue('Cajero')
  })
})

describe('Onboarding — skipping declares nothing (§6.1)', () => {
  it('"Lo hago luego" posts to /onboarding/skip with no answers', async () => {
    const user = userEvent.setup()
    serve()
    renderWizard()

    await screen.findByText('¿Cuál es tu puesto?')
    await user.click(screen.getByRole('button', { name: 'Lo hago luego' }))

    await waitFor(() => expect(postBodies('/onboarding/skip')).toHaveLength(1))
    expect(postBodies('/onboarding/skip')[0]).toBeUndefined()
    // No submission at all: the skip endpoint is the one that writes 'unknown'.
    expect(postBodies('/onboarding')).toHaveLength(0)
    expect(await screen.findByText('HOME')).toBeInTheDocument()
  })

  it('never sends experience_level: "none" when the learner did not declare it', async () => {
    const user = userEvent.setup()
    serve()
    renderWizard()

    await screen.findByText('¿Cuál es tu puesto?')
    await user.type(screen.getByRole('textbox'), 'Cajero')
    await user.click(screen.getByRole('button', { name: 'Continuar' }))

    await screen.findByText('¿Para qué quieres usar SkillNet ahora mismo?')
    await user.click(screen.getByRole('radio', { name: 'Me han asignado formación' }))
    // Bails out before the experience question.
    await user.click(screen.getByRole('button', { name: 'Lo hago luego' }))

    await waitFor(() => expect(postBodies('/onboarding/skip')).toHaveLength(1))
    const everyBody = JSON.stringify([...postBodies('/onboarding'), ...postBodies('/onboarding/skip')])
    expect(everyBody).not.toContain('experience_level')
    expect(everyBody).not.toContain('none')
  })

  it('does send "none" when the learner actually declared "Ninguna"', async () => {
    const user = userEvent.setup()
    serve()
    renderWizard()

    await screen.findByText('¿Cuál es tu puesto?')
    await user.type(screen.getByRole('textbox'), 'Cajero')
    await user.click(screen.getByRole('button', { name: 'Continuar' }))
    await screen.findByText('¿Para qué quieres usar SkillNet ahora mismo?')
    await user.click(screen.getByRole('radio', { name: 'Me han asignado formación' }))
    await user.click(screen.getByRole('button', { name: 'Continuar' }))
    await screen.findByText('¿Cuánta experiencia tienes en tu puesto actual?')
    await user.click(screen.getByRole('radio', { name: 'Ninguna' }))
    await user.click(screen.getByRole('button', { name: 'Continuar' }))
    await screen.findByText('¿Cómo prefieres estudiar?')
    await user.click(screen.getByRole('radio', { name: /Estándar/ }))
    await user.click(screen.getByRole('button', { name: 'Continuar' }))
    await screen.findByText('¿Qué formato te ayuda a empezar?')
    await user.click(screen.getByRole('button', { name: 'Continuar' }))
    await screen.findByText('¿Quieres activar algún ajuste de lectura?')
    await user.click(screen.getByRole('button', { name: 'Finalizar' }))

    await waitFor(() => expect(postBodies('/onboarding')).toHaveLength(1))
    expect(postBodies('/onboarding')[0]).toMatchObject({ experience_level: 'none' })
  })
})

describe('Onboarding — question 5 asks about needs, not conditions (§6.2, §6.3)', () => {
  it('offers the four reading settings and no "read aloud"', async () => {
    const user = userEvent.setup()
    serve()
    renderWizard()

    await screen.findByText('¿Cuál es tu puesto?')
    await user.type(screen.getByRole('textbox'), 'Cajero')
    await user.click(screen.getByRole('button', { name: 'Continuar' }))
    await screen.findByText('¿Para qué quieres usar SkillNet ahora mismo?')
    await user.click(screen.getByRole('radio', { name: 'Me han asignado formación' }))
    await user.click(screen.getByRole('button', { name: 'Continuar' }))
    await screen.findByText('¿Cuánta experiencia tienes en tu puesto actual?')
    await user.click(screen.getByRole('radio', { name: 'Algo' }))
    await user.click(screen.getByRole('button', { name: 'Continuar' }))
    await screen.findByText('¿Cómo prefieres estudiar?')
    await user.click(screen.getByRole('radio', { name: /Ritmo rápido/ }))
    await user.click(screen.getByRole('button', { name: 'Continuar' }))

    await screen.findByText('¿Qué formato te ayuda a empezar?')
    expect(screen.getByText(/Mezclaremos formatos/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Continuar' }))

    await screen.findByText('¿Quieres activar algún ajuste de lectura?')
    expect(screen.getAllByRole('checkbox')).toHaveLength(4)
    // No TTS in this PR, so no accommodation that does not exist.
    expect(screen.queryByText(/voz alta/i)).toBeNull()
    expect(screen.queryByText(/audio/i)).toBeNull()
    // And no diagnosis-shaped question.
    expect(screen.queryByText(/dislexia|TDAH|diagnóstic/i)).toBeNull()
  })

  it('drops an option whose key users.accessibility would reject', async () => {
    // Defensive: a server that ever offered "read aloud" would still not render it,
    // because the client only knows the four keys the column accepts.
    const user = userEvent.setup()
    mockFetch.mockImplementation((url: string) => {
      const path = String(url).replace('/api/v1', '')
      if (path === '/health') {
        return json({ status: 'ok', version: '0.1.0', database: 'connected' })
      }
      if (path === '/onboarding') {
        const questions = structuredClone(QUESTIONS)
        questions.questions[4].options?.push({ value: 'read_aloud', label: 'Leer en voz alta' })
        return json(questions)
      }
      return json({ detail: 'Not Found' }, 404)
    })
    renderWizard()

    await screen.findByText('¿Cuál es tu puesto?')
    await user.type(screen.getByRole('textbox'), 'Cajero')
    await user.click(screen.getByRole('button', { name: 'Continuar' }))
    await screen.findByText('¿Para qué quieres usar SkillNet ahora mismo?')
    await user.click(screen.getByRole('radio', { name: 'Me han asignado formación' }))
    await user.click(screen.getByRole('button', { name: 'Continuar' }))
    await screen.findByText('¿Cuánta experiencia tienes en tu puesto actual?')
    await user.click(screen.getByRole('radio', { name: 'Algo' }))
    await user.click(screen.getByRole('button', { name: 'Continuar' }))
    await screen.findByText('¿Cómo prefieres estudiar?')
    await user.click(screen.getByRole('radio', { name: /Estándar/ }))
    await user.click(screen.getByRole('button', { name: 'Continuar' }))

    await screen.findByText('¿Qué formato te ayuda a empezar?')
    await user.click(screen.getByRole('button', { name: 'Continuar' }))

    await screen.findByText('¿Quieres activar algún ajuste de lectura?')
    expect(screen.getAllByRole('checkbox')).toHaveLength(4)
    expect(screen.queryByText('Leer en voz alta')).toBeNull()
  })
})

describe('Onboarding — accessibility of the wizard itself', () => {
  it('moves focus to the new question so a keyboard user is not left behind', async () => {
    const user = userEvent.setup()
    serve()
    renderWizard()

    await screen.findByText('¿Cuál es tu puesto?')
    expect(currentStep()).toHaveAttribute('data-step', 'role_title')

    await user.type(screen.getByRole('textbox'), 'Cajero')
    await user.click(screen.getByRole('button', { name: 'Continuar' }))

    await screen.findByText('¿Para qué quieres usar SkillNet ahora mismo?')
    await waitFor(() => {
      expect(document.activeElement).toHaveAttribute('data-step', 'goal')
    })
  })

  it('advances on Enter from the text field — no mouse needed', async () => {
    const user = userEvent.setup()
    serve()
    renderWizard()

    await screen.findByText('¿Cuál es tu puesto?')
    await user.type(screen.getByRole('textbox'), 'Cajero{Enter}')
    expect(await screen.findByText('¿Para qué quieres usar SkillNet ahora mismo?')).toBeInTheDocument()
  })

  it('drops the slide entirely under prefers-reduced-motion', async () => {
    reduceMotion = true
    serve()
    renderWizard()

    await screen.findByText('¿Cuál es tu puesto?')
    // The animated branch is a motion.div, which writes inline transform/opacity.
    expect(currentStep()).not.toHaveAttribute('style')
  })

  it('animates the step swap when motion is allowed', async () => {
    reduceMotion = false
    serve()
    renderWizard()

    await screen.findByText('¿Cuál es tu puesto?')
    expect(currentStep()).toHaveAttribute('style')
  })
})

describe('Onboarding — error handling', () => {
  it('leaves for the app if the questions route answers 404', async () => {
    serve({ questionsStatus: 404 })
    renderWizard()
    expect(await screen.findByText('HOME')).toBeInTheDocument()
  })
})
