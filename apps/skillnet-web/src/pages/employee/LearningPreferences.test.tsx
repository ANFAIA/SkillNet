import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LearningPreferencesPage } from './LearningPreferences'

const mockFetch = vi.fn()

const PROFILE = {
  role_title: 'Cajero',
  sector: 'retail',
  goal: 'assigned',
  learning_note: null,
  experience_level: 'some',
  preset: 'standard',
  learning_preferences: {
    version: 3,
    web_presentation: 'visual',
    modalities: [],
    interaction: 'standard',
    detail: 'detailed',
    images: 'prefer',
  },
  nodes_completed: 4,
  onboarding_completed_at: '2026-08-11T12:00:00Z',
  onboarding_skipped: false,
  calibrating: false,
}

const USER = {
  id: 'u1',
  email: 'ada@test.dev',
  full_name: 'Ada',
  role: 'employee',
  accessibility: {
    short_blocks: true,
    reduce_motion: false,
    high_contrast: false,
    extra_time: false,
  },
}

function json(body: unknown, status = 200) {
  return Promise.resolve({ ok: status < 400, status, json: async () => body })
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <LearningPreferencesPage />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => vi.restoreAllMocks())

describe('LearningPreferencesPage', () => {
  it('loads current values and saves reversible preferences and accessibility', async () => {
    mockFetch.mockImplementation((input: string, options?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/users/me/learner-profile') && !options?.method) return json(PROFILE)
      if (url.endsWith('/auth/me')) return json(USER)
      if (url.endsWith('/users/me/learner-profile') && options?.method === 'PATCH') {
        return json({
          ...PROFILE,
          learning_preferences: JSON.parse(String(options.body)).learning_preferences,
        })
      }
      return json({ detail: 'Not Found' }, 404)
    })
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByRole('radio', { name: /Visual/ })).toBeChecked()
    expect(screen.getByRole('radio', { name: /Detallado/ })).toBeChecked()
    expect(screen.getByRole('radio', { name: /Preferir/ })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'Bloques mas cortos' })).toBeChecked()
    expect(screen.getByLabelText('Vista previa')).toBeInTheDocument()
    expect(screen.queryByText('En directo')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Audio/ }))
    await user.click(screen.getByRole('radio', { name: /Más práctica/ }))
    await user.click(screen.getByRole('radio', { name: /Conciso/ }))
    await user.click(screen.getByRole('radio', { name: /Evitar/ }))
    await user.click(screen.getByRole('checkbox', { name: 'Bloques mas cortos' }))

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('Preferencias guardadas')
    })
    const patchCall = mockFetch.mock.calls.find((call) => call[1]?.method === 'PATCH')
    expect(JSON.parse(patchCall?.[1]?.body as string)).toEqual({
      learning_preferences: {
        version: 3,
        web_presentation: 'visual',
        modalities: ['audio'],
        interaction: 'interactive',
        detail: 'concise',
        images: 'avoid',
      },
      accessibility: {
        short_blocks: false,
        reduce_motion: false,
        high_contrast: false,
        extra_time: false,
      },
      learning_note: null,
    })
    expect(mockFetch.mock.calls.some((call) => call[1]?.method === 'PUT')).toBe(false)
  })

  it('saves the free-text learning note', async () => {
    mockFetch.mockImplementation((input: string, options?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/users/me/learner-profile') && !options?.method) return json(PROFILE)
      if (url.endsWith('/auth/me')) return json(USER)
      if (url.endsWith('/users/me/learner-profile') && options?.method === 'PATCH') {
        return json({ ...PROFILE, learning_note: JSON.parse(String(options.body)).learning_note })
      }
      return json({ detail: 'Not Found' }, 404)
    })
    const user = userEvent.setup()
    renderPage()

    const note = await screen.findByLabelText('Como te gusta aprender')
    await user.type(note, 'me gustan las metaforas para aprender')

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('Preferencias guardadas')
    })
    const patchCall = mockFetch.mock.calls.find((call) => call[1]?.method === 'PATCH')
    expect(JSON.parse(patchCall?.[1]?.body as string).learning_note).toBe(
      'me gustan las metaforas para aprender',
    )
  })

  it('renders an inline error and retry action when loading fails', async () => {
    mockFetch.mockResolvedValue(json({ detail: 'boom' }, 500))
    renderPage()

    expect(await screen.findByText('No se pudieron cargar tus preferencias.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeInTheDocument()
  })
})
