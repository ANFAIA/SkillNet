import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Dashboard } from './Dashboard'

/**
 * The learner's home: the same node-based marker as the course list, plus the broken
 * Skill Map link this batch fixes.
 *
 * `/empleado/skills` is not a route (the real one is `/empleado/skillmap`), so the empty
 * Skill Map card used to fall through to `*` and dump the learner back at `/`. The test
 * asserts the destination rather than the click, because that failure was silent.
 */

const DYNAMIC_COURSE = '11111111-1111-4111-8111-111111111111'

const mockFetch = vi.fn()

function jsonResponse(status: number, body: unknown) {
  return Promise.resolve({
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
  })
}

function enrollment(overrides: Record<string, unknown> = {}) {
  return {
    id: 'e1',
    course_id: '22222222-2222-4222-8222-222222222222',
    user_id: 'u1',
    status: 'in_progress',
    deadline: null,
    score: null,
    progress: 0.4,
    course_title: 'Devoluciones en tienda',
    started_at: '2026-07-01T00:00:00Z',
    completed_at: null,
    delivery_mode: 'static',
    ...overrides,
  }
}

function installFetch(items: unknown[], skills: unknown[] = []) {
  mockFetch.mockImplementation((input: string) => {
    const url = String(input)
    if (url.endsWith('/health')) {
      return jsonResponse(200, {
        status: 'ok',
        version: '1',
        database: 'ok',
      })
    }
    if (url.endsWith('/auth/me')) {
      return jsonResponse(200, {
        id: 'u1',
        email: 'empleado@skillnet.dev',
        full_name: 'Empleada Ejemplo',
        role: 'employee',
      })
    }
    if (url.endsWith('/users/me/skills')) {
      return jsonResponse(200, skills)
    }
    if (url.includes('/enrollments')) {
      return jsonResponse(200, { items, total: items.length, page: 1, size: 20 })
    }
    return jsonResponse(404, { detail: 'Not Found', code: 'NOT_FOUND' })
  })
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/empleado']}>
        <Routes>
          <Route path="/empleado" element={<Dashboard />} />
          <Route path="/empleado/skillmap" element={<div>SKILLMAP</div>} />
          <Route path="/empleado/cursos" element={<div>MIS CURSOS</div>} />
          <Route path="/empleado/curso/:id" element={<div>CURSO</div>} />
          {/* Everything else lands here, the way the real `*` route does. */}
          <Route path="*" element={<div>FALLBACK</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Dashboard — node-based courses', () => {
  it('marks a course whose delivery_mode is dynamic', async () => {
    installFetch([
      enrollment({
        course_id: DYNAMIC_COURSE,
        course_title: 'Politica de devoluciones v2',
        delivery_mode: 'dynamic',
      }),
    ])
    renderPage()

    expect(await screen.findByText('Politica de devoluciones v2')).toBeInTheDocument()
    expect(screen.getByText('Por lecciones')).toBeInTheDocument()
  })

  it('leaves a static course unmarked', async () => {
    installFetch([enrollment()])
    renderPage()

    expect(await screen.findByText('Devoluciones en tienda')).toBeInTheDocument()
    expect(screen.queryByText('Por nodos')).toBeNull()
  })

  it('renders normalized enrollment scores as a percentage', async () => {
    installFetch([
      enrollment({
        status: 'completed',
        progress: 1,
        score: 0.925,
        completed_at: '2026-07-08T00:00:00Z',
      }),
    ])
    renderPage()

    expect(await screen.findByText('93%')).toBeInTheDocument()
  })
})

describe('Dashboard — the Skill Map link', () => {
  it('goes to /empleado/skillmap and not through the catch-all', async () => {
    installFetch([enrollment()], [])
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Ver Skill Map' }))

    expect(await screen.findByText('SKILLMAP')).toBeInTheDocument()
    expect(screen.queryByText('FALLBACK')).toBeNull()
  })
})
