import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { NodeView } from './NodeView'
import type {
  LearningNode,
  NodeList,
  NodeRenderAccepted,
  ProbeAnswerResult,
  ProbeSession,
} from '../../types'

/**
 * The node view, from the three angles where it can fail silently.
 *
 * 1. **A truncated stream must not explode.** The connection can end at any byte — mid
 *    `data:` line, after an `event:` with no payload, on invalid JSON — and every one of
 *    those has to leave the screen on the skeleton with `GET /render` still the source of
 *    truth. This is not a hypothetical: the pub/sub of §9.2 is in-memory, single worker,
 *    and keeps no backlog, so a reload or a redeploy cuts streams in the middle by
 *    construction.
 * 2. **A probe that declares mastery skips the node.** No render is ever requested, so no
 *    lesson is generated and no attempt is recorded — which is also what keeps
 *    `nodes_completed` where it was (transition 2 of §7.3 increments it only on
 *    `learning → mastered`; a skipped node produced no interaction event, and counting it
 *    would drop the learner out of calibration with an empty `format_vector`). The
 *    counter itself lives server-side; what is asserted here is the client half: nothing
 *    is posted that could count the node as worked.
 * 3. **The wait is productive** (§9.1). `render_hint: "prefetch"` fires `POST /render` in
 *    the background *while item B is still on screen*. If that stopped happening the
 *    product would still work and would simply be slow in a way no other test notices.
 */

const COURSE_ID = '11111111-1111-4111-8111-111111111111'
const NODE_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const NEXT_NODE_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
const RENDER_ID = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
const OLD_RENDER_ID = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd'
const PROBE_ID = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee'

const PROGRAM = [
  'root = Stack([intro], "md")',
  'intro = TextContent("El plazo de devolucion es de 30 dias.", "lead")',
].join('\n')

const SECOND_PROGRAM = [
  'root = Stack([intro], "md")',
  'intro = TextContent("Ahora con un ejemplo de caja.", "lead")',
].join('\n')

function learningNode(overrides: Partial<LearningNode> = {}): LearningNode {
  return {
    id: NODE_ID,
    title: 'Plazo de devolucion',
    summary: 'Cuantos dias tiene el cliente para devolver.',
    criticality: 'critical',
    position: 1,
    state: 'learning',
    mastery: 0.4,
    locked: false,
    locked_by: [],
    needs_practice: false,
    estimated_minutes: 6,
    ...overrides,
  }
}

function nodeList(node: LearningNode): NodeList {
  return {
    course_id: COURSE_ID,
    delivery_mode: 'dynamic',
    schema_version: 3,
    nodes: [
      node,
      learningNode({
        id: NEXT_NODE_ID,
        title: 'Excepciones',
        position: 2,
        state: 'not_started',
        mastery: 0,
      }),
    ],
    can_complete: false,
    blocked_by: [NODE_ID],
    progress_percent: 20,
  }
}

function probeSession(overrides: Partial<ProbeSession> = {}): ProbeSession {
  return {
    probe: {
      id: PROBE_ID,
      node_id: NODE_ID,
      schema_version: 3,
      attempt_no: 1,
      scored: true,
      score: null,
      mastered: null,
      tiebreak_used: false,
      created_at: '2026-07-26T09:00:00Z',
      completed_at: null,
    },
    items: [
      {
        item_id: 'a',
        item_type: 'test',
        bloom_level: 'apply',
        question: 'Un cliente vuelve a los 20 dias con el ticket. Que aplicas?',
        options: ['Devolucion', 'Garantia', 'Nada', 'Vale'],
      },
      {
        item_id: 'b',
        item_type: 'test',
        bloom_level: 'understand',
        question: 'Cuantos dias dura el plazo?',
        options: ['7', '15', '30', '60'],
      },
    ],
    reused: false,
    verdict: null,
    diagnostic: false,
    ...overrides,
  }
}

function probeAnswer(overrides: Partial<ProbeAnswerResult> = {}): ProbeAnswerResult {
  return {
    item_id: 'a',
    score: 1,
    passed: true,
    verdict: null,
    estimate: null,
    next_item_id: 'b',
    render_hint: null,
    feedback: null,
    ...overrides,
  }
}

// --------------------------------------------------------------------------- //
// fetch harness
// --------------------------------------------------------------------------- //

const mockFetch = vi.fn()

interface Scenario {
  node: LearningNode
  /** Consumed in order by `GET /nodes/{id}/render`; the last entry repeats. */
  renderResponses: Array<[number, unknown]>
  /** Consumed in order by `POST /nodes/{id}/render`; the last entry repeats. */
  accepted?: NodeRenderAccepted[]
  /** Raw SSE text chunks, delivered one `read()` at a time, then `done`. */
  streamChunks?: string[]
  probe?: ProbeSession
  probeAnswers?: ProbeAnswerResult[]
  renders?: Array<{ render_id: string; created_at: string | null; ui_format: string; status: string }>
  goal?: string | null
}

function jsonResponse(status: number, body: unknown) {
  return Promise.resolve({
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
  })
}

/** A real SSE body: one `read()` per chunk, so truncation is a short list. */
function sseResponse(chunks: string[]) {
  const encoder = new TextEncoder()
  let index = 0
  return Promise.resolve({
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: () =>
          index < chunks.length
            ? Promise.resolve({ done: false, value: encoder.encode(chunks[index++]) })
            : Promise.resolve({ done: true, value: undefined }),
      }),
    },
  })
}

function servedRender(program: string, renderId = RENDER_ID) {
  return {
    render_id: renderId,
    node_id: NODE_ID,
    ui_format: 'explanation',
    status: 'ready',
    backend: 'openui',
    cached: false,
    program,
  }
}

function installFetch(scenario: Scenario) {
  const renderQueue = [...scenario.renderResponses]
  const acceptedQueue = [...(scenario.accepted ?? [])]
  const answerQueue = [...(scenario.probeAnswers ?? [])]

  mockFetch.mockImplementation((input: string, init?: RequestInit) => {
    const url = String(input)
    const method = (init?.method ?? 'GET').toUpperCase()

    if (url.includes('/render/stream')) {
      return sseResponse(scenario.streamChunks ?? [])
    }
    if (url.endsWith(`/courses/${COURSE_ID}/nodes`)) {
      return jsonResponse(200, nodeList(scenario.node))
    }
    if (url.endsWith('/users/me/learner-profile')) {
      return jsonResponse(200, {
        role_title: 'Dependiente',
        sector: 'retail',
        goal: scenario.goal ?? 'specific_gap',
        experience_level: 'some',
        preset: 'standard',
        nodes_completed: 3,
        onboarding_completed_at: '2026-07-20T10:00:00Z',
        onboarding_skipped: false,
        calibrating: false,
      })
    }
    if (url.endsWith(`/nodes/${NODE_ID}/probe`) && method === 'POST') {
      return jsonResponse(200, scenario.probe ?? probeSession())
    }
    if (url.endsWith(`/nodes/${NODE_ID}/probe/answer`)) {
      const next = answerQueue.length > 1 ? answerQueue.shift() : answerQueue[0]
      return jsonResponse(200, next ?? probeAnswer())
    }
    if (url.endsWith(`/nodes/${NODE_ID}/render`) && method === 'POST') {
      const next = acceptedQueue.length > 1 ? acceptedQueue.shift() : acceptedQueue[0]
      return jsonResponse(202, next ?? { request_id: 'req-1', cached: false, render_id: null })
    }
    if (url.endsWith(`/nodes/${NODE_ID}/render`) && method === 'GET') {
      const next = renderQueue.length > 1 ? renderQueue.shift() : renderQueue[0]
      const [status, body] = next ?? [202, { status: 'pending', request_id: null }]
      return jsonResponse(status, body)
    }
    if (url.endsWith(`/nodes/${NODE_ID}/renders`)) {
      return jsonResponse(200, { renders: scenario.renders ?? [] })
    }
    if (url.endsWith(`/nodes/${NODE_ID}/events`) || url.endsWith(`/nodes/${NODE_ID}/feedback`)) {
      return jsonResponse(204, null)
    }
    if (url.includes('/explain')) {
      return sseResponse([
        `event: token\ndata: ${JSON.stringify({ content: 'Los dias naturales cuentan fines de semana.' })}\n\n`,
        `event: done\ndata: ${JSON.stringify({ explanation: 'Los dias naturales cuentan fines de semana.', cached: false })}\n\n`,
      ])
    }
    return jsonResponse(404, { detail: 'Not Found', code: 'NOT_FOUND' })
  })
}

function callsTo(fragment: string, method = 'GET') {
  return mockFetch.mock.calls.filter((call) => {
    const url = String(call[0])
    const used = ((call[1] as RequestInit | undefined)?.method ?? 'GET').toUpperCase()
    return url.includes(fragment) && used === method
  })
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/empleado/curso/${COURSE_ID}/nodo/${NODE_ID}`]}>
        <Routes>
          <Route path="/empleado/curso/:id/nodo/:nodeId" element={<NodeView />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

let warnSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
  warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
})

afterEach(() => {
  warnSpy.mockRestore()
  vi.restoreAllMocks()
})

// --------------------------------------------------------------------------- //

describe('NodeView — the frozen frame', () => {
  it('keeps the title, the progress bar and the navigation in every phase', async () => {
    installFetch({
      node: learningNode({ state: 'not_started' }),
      renderResponses: [[202, { status: 'pending', request_id: null }]],
    })
    renderPage()

    // Probe phase: the frame is already there, before any content exists.
    expect(await screen.findByRole('heading', { name: 'Plazo de devolucion' })).toBeInTheDocument()
    expect(screen.getByText('Nodo 1 de 2 · 6 min')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Anterior' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Siguiente' })).toBeInTheDocument()
  })

  it('renders the deterministic opening line from `goal`, never from the model', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [[200, servedRender(PROGRAM)]],
      goal: 'specific_gap',
    })
    renderPage()

    expect(await screen.findByTestId('opening-line')).toHaveTextContent(
      'Esto te sirve para dominar lo que viniste a resolver.',
    )
  })
})

describe('NodeView — streaming', () => {
  it('paints the program once `ui_done` lands, not the streamed blocks', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [
        [202, { status: 'pending', request_id: null }],
        [200, servedRender(PROGRAM)],
      ],
      accepted: [{ request_id: 'req-1', cached: false, render_id: null }],
      streamChunks: [
        `event: render_step\ndata: ${JSON.stringify({ step: 'genera_ui', message: 'Escribiendo la leccion...' })}\n\n`,
        `event: ui_format\ndata: ${JSON.stringify({ format: 'explanation', tier: 'heavy' })}\n\n`,
        `event: ui_block\ndata: ${JSON.stringify({ component: { id: 'intro', type: 'TextContent' } })}\n\n`,
        `event: ui_done\ndata: ${JSON.stringify({ render_id: RENDER_ID, format: 'explanation', status: 'ready' })}\n\n`,
      ],
    })
    const { container } = renderPage()

    await waitFor(() => expect(container).toHaveTextContent('El plazo de devolucion es de 30 dias.'))
    // The `ui_block` payload is a pre-gate component dict; it must never be rendered, so
    // its own type name cannot appear on screen.
    expect(container).not.toHaveTextContent('TextContent')
    expect(screen.queryByTestId('node-skeleton')).not.toBeInTheDocument()
  })

  it('shows the step message and the format-shaped skeleton while it waits', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [[202, { status: 'pending', request_id: null }]],
      accepted: [{ request_id: 'req-1', cached: false, render_id: null }],
      streamChunks: [
        `event: render_step\ndata: ${JSON.stringify({ step: 'genera_ui', message: 'Escribiendo la leccion...' })}\n\n`,
        `event: ui_format\ndata: ${JSON.stringify({ format: 'exercise', tier: 'heavy' })}\n\n`,
        `event: ui_block\ndata: ${JSON.stringify({ component: { id: 'q1', type: 'QuizItem' } })}\n\n`,
      ],
    })
    renderPage()

    // Re-queried inside `waitFor`: the first skeleton on screen belongs to the node-list
    // loading state, and the content one is a different element.
    await waitFor(() =>
      expect(screen.getByTestId('node-skeleton')).toHaveAttribute('data-ui-format', 'exercise'),
    )
    const skeleton = screen.getByTestId('node-skeleton')
    expect(skeleton).toHaveTextContent('Escribiendo la leccion...')
    expect(skeleton).toHaveTextContent('1 bloque listo')
  })

  /**
   * Each case is the same stream cut at a different byte. The assertion is identical on
   * purpose: still on the skeleton, no error card, nothing thrown.
   */
  const truncations: Array<[string, string[]]> = [
    ['cut in the middle of an event name', [
      `event: render_step\ndata: ${JSON.stringify({ step: 'genera_ui', message: 'Escribiendo la leccion...' })}\n\n`,
      'event: ui_for',
    ]],
    ['cut in the middle of a data payload', [
      `event: ui_format\ndata: ${JSON.stringify({ format: 'explanation', tier: 'fast' })}\n\n`,
      'event: ui_block\ndata: {"component": {"id": "int',
    ]],
    ['an event line with no data line at all', [
      `event: ui_format\ndata: ${JSON.stringify({ format: 'explanation', tier: 'fast' })}\n\n`,
      'event: ui_done\n',
    ]],
    ['a data line that is not JSON', [
      `event: ui_format\ndata: ${JSON.stringify({ format: 'explanation', tier: 'fast' })}\n\n`,
      'event: ui_block\ndata: {{{not json}}}\n\n',
    ]],
    ['nothing at all before the connection dies', []],
  ]

  it.each(truncations)('survives a stream %s', async (_name, chunks) => {
    installFetch({
      node: learningNode(),
      renderResponses: [[202, { status: 'pending', request_id: null }]],
      accepted: [{ request_id: 'req-1', cached: false, render_id: null }],
      streamChunks: chunks,
    })
    renderPage()

    expect(await screen.findByTestId('node-skeleton')).toBeInTheDocument()
    // A cut stream is not a failed render: the graph is still running server-side and
    // `GET /render` remains the source of truth, so no failure sentence is shown.
    expect(screen.queryByText('No se pudo preparar esta leccion.')).not.toBeInTheDocument()
  })

  it('asks for the seed after `error` with `fallback: true`', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [
        [202, { status: 'pending', request_id: null }],
        [200, servedRender(PROGRAM)],
      ],
      accepted: [{ request_id: 'req-1', cached: false, render_id: null }],
      streamChunks: [
        `event: error\ndata: ${JSON.stringify({ step: 'genera_ui', message: 'El modelo fallo', fallback: true })}\n\n`,
      ],
    })
    const { container } = renderPage()

    await waitFor(() => expect(container).toHaveTextContent('El plazo de devolucion es de 30 dias.'))
  })

  it('does not retry after `error` with `fallback: false`', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [[202, { status: 'pending', request_id: null }]],
      accepted: [{ request_id: 'req-1', cached: false, render_id: null }],
      streamChunks: [
        `event: error\ndata: ${JSON.stringify({ step: 'validate_ui', message: 'Sin contenido', fallback: false })}\n\n`,
      ],
    })
    renderPage()

    expect(await screen.findByText('No se pudo preparar esta leccion.')).toBeInTheDocument()
    // One POST, and no second one: there is nothing to serve and a retry loop against a
    // blank screen is the failure this branch exists to prevent.
    const posts = callsTo(`/nodes/${NODE_ID}/render`, 'POST')
    expect(posts).toHaveLength(1)
    await waitFor(() => expect(callsTo(`/nodes/${NODE_ID}/render`, 'POST')).toHaveLength(1))
  })

  it('never subscribes when the render was already cached', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [
        [202, { status: 'pending', request_id: null }],
        [200, servedRender(PROGRAM)],
      ],
      accepted: [{ request_id: '', cached: true, render_id: RENDER_ID }],
    })
    const { container } = renderPage()

    await waitFor(() => expect(container).toHaveTextContent('El plazo de devolucion es de 30 dias.'))
    expect(callsTo('/render/stream')).toHaveLength(0)
  })
})

describe('NodeView — the probe is the productive wait', () => {
  it('fires the background render while item B is still on screen', async () => {
    installFetch({
      node: learningNode({ state: 'not_started' }),
      renderResponses: [[202, { status: 'pending', request_id: null }]],
      accepted: [{ request_id: 'req-1', cached: false, render_id: null }],
      probeAnswers: [
        probeAnswer({ item_id: 'a', score: 0, passed: false, render_hint: 'prefetch' }),
      ],
      streamChunks: [],
    })
    renderPage()

    await screen.findByTestId('probe-runner')
    expect(callsTo(`/nodes/${NODE_ID}/render`, 'POST')).toHaveLength(0)

    await userEvent.click(screen.getByText('Garantia'))
    await userEvent.click(screen.getByRole('button', { name: 'Responder' }))

    // Item B is on screen and the render is already being generated behind it. That
    // overlap is the whole latency strategy of §9.1.
    expect(await screen.findByText('Cuantos dias dura el plazo?')).toBeInTheDocument()
    await waitFor(() => expect(callsTo(`/nodes/${NODE_ID}/render`, 'POST')).toHaveLength(1))
  })

  it('skips the node when the probe declares mastery, and generates nothing', async () => {
    installFetch({
      node: learningNode({ state: 'not_started' }),
      renderResponses: [[202, { status: 'pending', request_id: null }]],
      probeAnswers: [
        probeAnswer({ item_id: 'a', next_item_id: 'b' }),
        probeAnswer({
          item_id: 'b',
          verdict: 'mastered',
          estimate: 1,
          next_item_id: null,
          render_hint: 'skip',
        }),
      ],
    })
    renderPage()

    await screen.findByTestId('probe-runner')
    await userEvent.click(screen.getByText('Devolucion'))
    await userEvent.click(screen.getByRole('button', { name: 'Responder' }))

    await screen.findByText('Cuantos dias dura el plazo?')
    await userEvent.click(screen.getByText('30'))
    await userEvent.click(screen.getByRole('button', { name: 'Responder' }))

    expect(await screen.findByText('Ya dominas este nodo')).toBeInTheDocument()

    // Nothing was generated, nothing was streamed, and nothing was graded: a node skipped
    // by the probe is exactly the node that must not count as worked (§3.3, §7.3 rule 2).
    expect(callsTo(`/nodes/${NODE_ID}/render`, 'POST')).toHaveLength(0)
    expect(callsTo(`/nodes/${NODE_ID}/render`)).toHaveLength(0)
    expect(callsTo('/render/stream')).toHaveLength(0)
    expect(callsTo(`/nodes/${NODE_ID}/answer`, 'POST')).toHaveLength(0)
  })

  it('frames the unscored diagnostic probe as such', async () => {
    installFetch({
      node: learningNode({ state: 'not_started' }),
      renderResponses: [[202, { status: 'pending', request_id: null }]],
      probe: probeSession({ diagnostic: true }),
    })
    renderPage()

    expect(await screen.findByText('Vamos a ver que te suena ya')).toBeInTheDocument()
    expect(
      screen.getByText('No cuenta para tu nota: solo sirve para no explicarte lo que ya sabes.'),
    ).toBeInTheDocument()
  })
})

describe('NodeView — the two control affordances (§5.5)', () => {
  it('offers "Actualizar esta leccion" and says it is the only thing that changes it', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [[200, servedRender(PROGRAM)]],
      renders: [
        { render_id: RENDER_ID, created_at: '2026-07-26T09:00:00Z', ui_format: 'explanation', status: 'ready' },
      ],
    })
    renderPage()

    const controls = await screen.findByTestId('render-controls')
    expect(
      screen.getByRole('button', { name: 'Actualizar esta leccion' }),
    ).toBeInTheDocument()
    expect(controls).toHaveTextContent(
      'Solo este boton cambia el contenido de este nodo.',
    )
    // With only the pinned version served, there is no previous version to offer yet.
    expect(screen.queryByRole('button', { name: 'Ver la version anterior' })).toBeNull()
  })

  it('regenerating shows the adaptation notice and a way back to the replaced version', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [
        [200, servedRender(PROGRAM)],
        [200, servedRender(SECOND_PROGRAM, OLD_RENDER_ID)],
      ],
      accepted: [{ request_id: 'req-2', cached: false, render_id: null }],
      streamChunks: [
        `event: ui_done\ndata: ${JSON.stringify({ render_id: OLD_RENDER_ID, format: 'explanation', status: 'ready' })}\n\n`,
      ],
      renders: [
        { render_id: OLD_RENDER_ID, created_at: '2026-07-26T11:00:00Z', ui_format: 'explanation', status: 'ready' },
        { render_id: RENDER_ID, created_at: '2026-07-26T09:00:00Z', ui_format: 'explanation', status: 'ready' },
      ],
    })
    const { container } = renderPage()

    await screen.findByTestId('render-controls')
    await userEvent.click(screen.getByRole('button', { name: 'Actualizar esta leccion' }))

    await waitFor(() => expect(container).toHaveTextContent('Ahora con un ejemplo de caja.'))
    expect(
      screen.getByText('Esta leccion se ha adaptado a tus ultimas respuestas.'),
    ).toBeInTheDocument()

    // The version that was replaced is still viewable in this session.
    await userEvent.click(screen.getByRole('button', { name: 'Ver la version anterior' }))
    await userEvent.click(screen.getByRole('button', { name: /^Version del/ }))
    await waitFor(() =>
      expect(container).toHaveTextContent('El plazo de devolucion es de 30 dias.'),
    )
    expect(screen.getByText('Estas viendo una version anterior.')).toBeInTheDocument()

    // The forced render went out with `force: true` — the only recomputing call (§5.5).
    const force = callsTo(`/nodes/${NODE_ID}/render`, 'POST').at(-1)
    expect(force).toBeDefined()
    const body = (force?.[1] as RequestInit | undefined)?.body
    expect(JSON.parse(String(body))).toEqual({ force: true, preview: false })
  })
})

describe('NodeView — click to explain (§8.5)', () => {
  it('explains a word in the lesson but not a click on a control', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [[200, servedRender(PROGRAM)]],
    })
    const { container } = renderPage()

    await waitFor(() => expect(container).toHaveTextContent('El plazo de devolucion es de 30 dias.'))

    // A control inside the same subtree is not a term: no popover, no `/explain`.
    await userEvent.click(screen.getByRole('button', { name: 'Actualizar esta leccion' }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(callsTo('/explain', 'POST')).toHaveLength(0)

    await userEvent.click(screen.getByText('devolucion'))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(callsTo('/explain', 'POST')).toHaveLength(1)
  })
})

describe('NodeView — an unreviewed node', () => {
  it('explains the 409 instead of retrying against a blank screen', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [
        [409, { detail: 'not reviewed', code: 'CONFLICT', field: 'node_not_reviewed' }],
      ],
    })
    renderPage()

    expect(await screen.findByText('Este nodo esta pendiente de revision')).toBeInTheDocument()
    expect(callsTo(`/nodes/${NODE_ID}/render`, 'POST')).toHaveLength(0)
  })
})
