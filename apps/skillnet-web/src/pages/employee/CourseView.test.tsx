import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom'
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
  /** `GET /courses/{id}/progress` rows. Empty means "nothing completed yet". */
  progressLessons?: unknown[]
}

function installFetch({ nodes, progressLessons = [] }: Options) {
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
        lessons: progressLessons,
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
    next_node_id: null,
    nodes: [
      {
        id: NODE_ID,
        title: 'Plazo de devolucion',
        summary: 'Cuantos dias tiene el cliente.',
        criticality: 'critical',
        position: 1,
        state: 'not_started',
        mastery: 0,
        first_seen_at: null as string | null,
      },
    ],
    can_complete: false,
    blocked_by: [NODE_ID],
    progress_percent: 0,
  }
}

/** Stands in for `NodeView`, and names the node it was handed. */
function NodeViewStub() {
  const { nodeId } = useParams<{ nodeId: string }>()
  return <div data-testid="node-view">{nodeId}</div>
}

function renderPage(entry: string | { pathname: string; state: unknown } = `/empleado/curso/${COURSE_ID}`) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/empleado/curso/:id" element={<CourseView />} />
          <Route path="/empleado/curso/:id/nodo/:nodeId" element={<NodeViewStub />} />
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
  it('prepares exactly the first two available lessons when the course opens', async () => {
    const dynamic = nodeList('dynamic')
    dynamic.nodes = Array.from({ length: 4 }, (_, index) => ({
      ...dynamic.nodes[0],
      id: `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa${index}`,
      title: `Leccion ${index + 1}`,
      position: index + 1,
    }))
    installFetch({ nodes: dynamic })
    renderPage()

    await screen.findByRole('heading', { name: 'Devoluciones en tienda' })
    await waitFor(() => {
      const renderCalls = mockFetch.mock.calls.filter(([input, init]) =>
        String(input).includes('/nodes/') && String(input).endsWith('/render') && init?.method === 'POST',
      )
      expect(renderCalls).toHaveLength(2)
      expect(renderCalls.map(([input]) => String(input))).toEqual([
        expect.stringContaining('/nodes/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa0/render'),
        expect.stringContaining('/nodes/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1/render'),
      ])
    })
  })

  it('renders the overview and opens the first unlocked node from its main action', async () => {
    installFetch({ nodes: nodeList('dynamic') })
    renderPage()

    expect(await screen.findByRole('heading', { name: 'Devoluciones en tienda' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Índice' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Resúmenes' })).toBeInTheDocument()
    expect(screen.queryByTestId('node-view')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /Empezar/ }))
    expect(await screen.findByTestId('node-view')).toBeInTheDocument()
  })

  it('keeps the full node map available from the overview', async () => {
    installFetch({ nodes: nodeList('dynamic') })
    renderPage()

    expect(await screen.findByRole('list')).toBeInTheDocument()
    expect(screen.getByText('Plazo de devolucion')).toBeInTheDocument()
    // The v1 tree is gone, not hidden behind it.
    expect(screen.queryByText('Modulo de devoluciones')).toBeNull()
  })

  it('opens the course tutor with course-wide context', async () => {
    installFetch({ nodes: nodeList('dynamic') })
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: 'Preguntar al tutor' }))
    expect(screen.getByRole('dialog', { name: 'Tutor del curso' })).toBeInTheDocument()
    expect(
      screen.getByText('Pregunta cualquier duda sobre el curso, aunque todavía no hayas llegado a ese tema.'),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '¿Qué debo saber de este curso?' }))

    await waitFor(() => {
      const chatCall = mockFetch.mock.calls.find(([input]) => String(input).endsWith('/chat'))
      expect(chatCall).toBeDefined()
      const body = JSON.parse(String(chatCall?.[1]?.body)) as Record<string, unknown>
      expect(body).toMatchObject({ context: { course_id: COURSE_ID } })
      expect(body).not.toHaveProperty('context.node_id')
    })
  })

  it('never flashes the v1 tree before the node map lands', async () => {
    installFetch({ nodes: nodeList('dynamic') })
    renderPage()

    // While the node list is in flight the screen is the skeleton, never the module tree:
    // painting v1 and replacing it is the layout jump §5.5 forbids.
    expect(screen.queryByText('Modulo de devoluciones')).toBeNull()
    await waitFor(() => expect(screen.getByText('Plazo de devolucion')).toBeInTheDocument())
    expect(screen.queryByText('Modulo de devoluciones')).toBeNull()
  })
})

/**
 * "Salgo y vuelvo a entrar y no se ha guardado por donde iba."
 *
 * Both halves of the fix are observable from this screen: the v1 lesson chain, which had
 * `courseProgress.lessons[].completed` loaded and never read it, and the v2 overview,
 * whose "Continuar" button used to guess the target from `state`.
 */
describe('CourseView — coming back to a course', () => {
  function lessonProgress(lessonId: string, completed: boolean) {
    return {
      lesson_id: lessonId,
      completed,
      exercises_pending: 0,
      exercises_total: 0,
      exercises_passed: 0,
    }
  }

  it('v1: opens the first lesson the learner has NOT completed', async () => {
    installFetch({
      nodes: null,
      progressLessons: [lessonProgress('lesson-1', true), lessonProgress('lesson-2', false)],
    })
    renderPage()

    // The open lesson is the heading in the content column; the sidebar renders buttons.
    expect(await screen.findByRole('heading', { name: 'Excepciones' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Plazo legal' })).toBeNull()
  })

  it('v1: opens the last lesson when every lesson is already completed', async () => {
    installFetch({
      nodes: null,
      progressLessons: [lessonProgress('lesson-1', true), lessonProgress('lesson-2', true)],
    })
    renderPage()

    expect(await screen.findByRole('heading', { name: 'Excepciones' })).toBeInTheDocument()
  })

  it('v1: still opens the first lesson when nothing is completed', async () => {
    installFetch({ nodes: null, progressLessons: [] })
    renderPage()

    expect(await screen.findByRole('heading', { name: 'Plazo legal' })).toBeInTheDocument()
  })

  it('v2: the main action opens the deepest node seen, not the first one', async () => {
    const dynamic = nodeList('dynamic')
    dynamic.nodes = [
      { ...dynamic.nodes[0], id: 'n1', title: 'Leccion 1', position: 1, first_seen_at: '2026-08-20T09:00:00Z' },
      { ...dynamic.nodes[0], id: 'n2', title: 'Leccion 2', position: 2, first_seen_at: '2026-08-22T09:00:00Z' },
      { ...dynamic.nodes[0], id: 'n3', title: 'Leccion 3', position: 3, first_seen_at: null },
    ]
    dynamic.progress_percent = 40
    installFetch({ nodes: dynamic })
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: /Continuar/ }))
    // `state` is `not_started` on all three — which is exactly why the old chain of
    // `find`s always landed on the first node.
    expect(await screen.findByTestId('node-view')).toHaveTextContent('n2')
  })

  it('v2: forwards straight to that node when asked to resume', async () => {
    const dynamic = nodeList('dynamic')
    dynamic.nodes = [
      { ...dynamic.nodes[0], id: 'n1', title: 'Leccion 1', position: 1, first_seen_at: '2026-08-20T09:00:00Z' },
      { ...dynamic.nodes[0], id: 'n2', title: 'Leccion 2', position: 2, first_seen_at: '2026-08-22T09:00:00Z' },
    ]
    installFetch({ nodes: dynamic })
    renderPage({ pathname: `/empleado/curso/${COURSE_ID}`, state: { resume: true } })

    // No click: the home hero's "Continuar" passes the intent in the route state, because
    // it has no node list of its own and fetching one would cost a request per course.
    expect(await screen.findByTestId('node-view')).toHaveTextContent('n2')
  })

  it('v2: does not forward when the course page is opened normally', async () => {
    installFetch({ nodes: nodeList('dynamic') })
    renderPage()

    expect(await screen.findByRole('heading', { name: 'Devoluciones en tienda' })).toBeInTheDocument()
    expect(screen.queryByTestId('node-view')).toBeNull()
  })
})
