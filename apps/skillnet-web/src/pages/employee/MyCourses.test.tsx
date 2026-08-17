import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MyCourses } from './MyCourses'

/**
 * Telling the two kinds of course apart from the list.
 *
 * A node-based course opens as a map of nodes instead of a chain of lessons, and until
 * now the list gave the learner no way to know which was which. The discriminator is
 * `EnrollmentRead.delivery_mode`, which the server only reports as `'dynamic'` when the
 * schema is validated **and** the flag is `on` — so the marker cannot appear for a v1
 * course, and no extra client-side gate is needed.
 */

const DYNAMIC_COURSE = '11111111-1111-4111-8111-111111111111'
const STATIC_COURSE = '22222222-2222-4222-8222-222222222222'

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
    course_id: STATIC_COURSE,
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

function installFetch(items: unknown[]) {
  mockFetch.mockImplementation((input: string) => {
    const url = String(input)
    if (url.endsWith('/health')) {
      return jsonResponse(200, {
        status: 'ok',
        version: '1',
        database: 'ok',
      })
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
      <MemoryRouter initialEntries={['/empleado/cursos']}>
        <Routes>
          <Route path="/empleado/cursos" element={<MyCourses />} />
          <Route path="/empleado/curso/:id" element={<div>CURSO</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/**
 * The list lands on **Pendientes** since `dbd7804`, and these fixtures are courses already
 * under way — which is the state a node-based course spends its life in, so changing them
 * to make the landing tab do the work would be testing the marker on the wrong course.
 * Every test therefore opens the tab its fixtures live in first.
 */
async function openInProgress() {
  await userEvent.click(screen.getByRole('button', { name: 'En progreso' }))
}

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('MyCourses — node-based courses', () => {
  it('marks a course whose delivery_mode is dynamic', async () => {
    installFetch([
      enrollment({
        id: 'e2',
        course_id: DYNAMIC_COURSE,
        course_title: 'Politica de devoluciones v2',
        delivery_mode: 'dynamic',
      }),
    ])
    renderPage()
    await openInProgress()

    expect(await screen.findByText('Politica de devoluciones v2')).toBeInTheDocument()
    expect(screen.getByText('Por lecciones')).toBeInTheDocument()
  })

  it('leaves a static course unmarked', async () => {
    installFetch([enrollment()])
    renderPage()
    await openInProgress()

    expect(await screen.findByText('Devoluciones en tienda')).toBeInTheDocument()
    expect(screen.queryByText('Por nodos')).toBeNull()
  })

  it('marks only the dynamic one when both kinds are enrolled', async () => {
    installFetch([
      enrollment(),
      enrollment({
        id: 'e2',
        course_id: DYNAMIC_COURSE,
        course_title: 'Politica de devoluciones v2',
        delivery_mode: 'dynamic',
      }),
    ])
    renderPage()
    await openInProgress()

    await screen.findByText('Devoluciones en tienda')
    expect(screen.getAllByText('Por lecciones')).toHaveLength(1)
  })

  it('still opens the course, which is where the node map lives', async () => {
    installFetch([
      enrollment({
        id: 'e2',
        course_id: DYNAMIC_COURSE,
        course_title: 'Politica de devoluciones v2',
        delivery_mode: 'dynamic',
      }),
    ])
    renderPage()
    await openInProgress()

    await userEvent.click(await screen.findByText('Politica de devoluciones v2'))
    expect(await screen.findByText('CURSO')).toBeInTheDocument()
  })
})
