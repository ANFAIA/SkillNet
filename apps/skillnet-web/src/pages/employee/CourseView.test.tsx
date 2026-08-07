import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CourseView } from './CourseView'

/**
 * The v2 branch of `CourseView`, and the regression it must not cause.
 *
 * A dynamic course renders `NodeList`, anything else renders the v1 tree **intact**.
 * The tests below are the proof of the second half, which is the half that can break
 * silently — a v1 course served today by this screen has to look exactly as it did
 * before v2 existed.
 *
 * The discriminator under test is `GET /courses/{id}/nodes`, not `course.delivery_mode`:
 * `CourseRead` has no such field, and the node list is the route that answers only for
 * a dynamic course with a validated schema — exactly `resolve_delivery`'s conditions.
 */

const COURSE_ID = '11111111-1111-4111-8111-111111111111'
const NODE_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

const mockFetch = vi.fn()

function jsonResponse(status: number, body: unknown) {
  return Promise.resolve({
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
  })
}

const V1_COURSE = {
  id: COURSE_ID,
  title: 'Devoluciones en tienda',
  description: null,
  outcome: null,
  status: 'published',
  source_document_id: null,
  created_at: '2026-07-01T00:00:00Z',
  module_count: 1,
  modules: [
    {
      id: 'mod-1',
      title: 'Modulo de devoluciones',
      summary: null,
      position: 1,
      lessons: [
        {
          id: 'lesson-1',
          title: 'Plazo legal',
          content: 'Se aceptan devoluciones durante 30 dias naturales.',
          position: 1,
          exercises: [],
        },
        {
          id: 'lesson-2',
          title: 'Excepciones',
          content: 'Los productos perecederos no se devuelven.',
          position: 2,
          exercises: [],
        },
      ],
    },
  ],
}

interface Options {
  /** `null` → the node route 404s (static course). */
  nodes: unknown | null
}

function installFetch({ nodes }: Options) {
  mockFetch.mockImplementation((input: string) => {
    const url = String(input)

    if (url.endsWith('/health')) {
      return jsonResponse(200, {
        status: 'ok',
        version: '1',
        database: 'ok',
      })
    }
    if (url.endsWith(`/courses/${COURSE_ID}/nodes`)) {
      if (nodes === null) return jsonResponse(404, { detail: 'Not Found', code: 'NOT_FOUND' })
      return jsonResponse(200, nodes)
    }
    if (url.endsWith(`/courses/${COURSE_ID}/progress`)) {
      return jsonResponse(200, {
        course_id: COURSE_ID,
        progress_percent: 0,
        lessons: [],
        can_complete: false,
      })
    }
    if (url.includes('/enrollments')) {
      return jsonResponse(200, { items: [], total: 0, page: 1, size: 20 })
    }
    if (url.endsWith(`/courses/${COURSE_ID}`)) {
      return jsonResponse(200, V1_COURSE)
    }
    return jsonResponse(404, { detail: 'Not Found', code: 'NOT_FOUND' })
  })
}

function nodeList(deliveryMode: 'static' | 'dynamic') {
  return {
    course_id: COURSE_ID,
    delivery_mode: deliveryMode,
    schema_version: 3,
    nodes: [
      {
        id: NODE_ID,
        title: 'Plazo de devolucion',
        summary: 'Cuantos dias tiene el cliente.',
        criticality: 'critical',
        position: 1,
        state: 'not_started',
        mastery: 0,
        locked: false,
        locked_by: [],
        needs_practice: false,
        estimated_minutes: 6,
      },
    ],
    can_complete: false,
    blocked_by: [NODE_ID],
    progress_percent: 0,
  }
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/empleado/curso/${COURSE_ID}`]}>
        <Routes>
          <Route path="/empleado/curso/:id" element={<CourseView />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** The v1 tree, identified by the parts only it has. */
async function expectV1Tree() {
  expect(await screen.findByText('Modulo de devoluciones')).toBeInTheDocument()
  // "Plazo legal" is both the sidebar entry and the open lesson's heading, which is the
  // v1 layout: a module list on the left, the active lesson on the right.
  // Awaited, not queried: the first module is expanded by a passive effect, which can
  // land a tick after the module title is already in the DOM.
  expect(await screen.findByRole('button', { name: 'Plazo legal' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Plazo legal' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Excepciones' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Siguiente' })).toBeInTheDocument()
  expect(screen.queryByTestId('node-list')).toBeNull()
}

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('CourseView — v1 non-regression', () => {
  it('renders exactly the v1 tree when `delivery_mode` is static', async () => {
    installFetch({ nodes: nodeList('static') })
    renderPage()

    await expectV1Tree()
  })

  it('renders the v1 tree when the node route 404s (course never migrated)', async () => {
    installFetch({ nodes: null })
    renderPage()

    await expectV1Tree()
  })
})

describe('CourseView — the dynamic branch', () => {
  it('renders the node map, linking each node to its own screen', async () => {
    installFetch({ nodes: nodeList('dynamic') })
    renderPage()

    // A fresh course (0 mastered) shows a welcome screen first; click "Empezar"
    // to get past it to the node list.
    await userEvent.click(await screen.findByRole('button', { name: 'Empezar' }))

    expect(await screen.findByTestId('node-list')).toBeInTheDocument()
    expect(screen.getByText('Plazo de devolucion')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Plazo de devolucion/ })).toHaveAttribute(
      'href',
      `/empleado/curso/${COURSE_ID}/nodo/${NODE_ID}`,
    )
    // The v1 tree is gone, not hidden behind it.
    expect(screen.queryByText('Modulo de devoluciones')).toBeNull()
    // And the course cannot close in silence: the blocking node is named (§7.4).
    expect(
      screen.getByText('Para completar el curso te falta: Plazo de devolucion.'),
    ).toBeInTheDocument()
  })

  it('never flashes the v1 tree before the node map lands', async () => {
    installFetch({ nodes: nodeList('dynamic') })
    renderPage()

    // While the node list is in flight the screen is the skeleton, never the module tree:
    // painting v1 and replacing it is the layout jump §5.5 forbids.
    expect(screen.queryByText('Modulo de devoluciones')).toBeNull()
    // The welcome screen comes first for fresh courses (0 mastered); dismiss it.
    await userEvent.click(await screen.findByRole('button', { name: 'Empezar' }))
    await waitFor(() => expect(screen.getByTestId('node-list')).toBeInTheDocument())
    expect(screen.queryByText('Modulo de devoluciones')).toBeNull()
  })
})
