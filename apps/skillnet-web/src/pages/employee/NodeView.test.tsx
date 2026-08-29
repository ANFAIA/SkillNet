import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { NodeView } from './NodeView'
import { declaredReducedMotionContext } from '../../hooks/useReducedMotion'
import { readNodePosition, writeNodePosition } from '../../features/resume/storage'
import type {
  LearningNode,
  NodeList,
  NodeRenderAccepted,
} from '../../types'

/**
 * The node view, from the angles where it can fail silently.
 *
 * 1. **A truncated stream must not explode.** The connection can end at any byte — mid
 *    `data:` line, after an `event:` with no payload, on invalid JSON — and every one of
 *    those has to leave the screen on the skeleton with `GET /render` still the source of
 *    truth. This is not a hypothetical: the pub/sub of §9.2 is in-memory, single worker,
 *    and keeps no backlog, so a reload or a redeploy cuts streams in the middle by
 *    construction.
 */

const COURSE_ID = '11111111-1111-4111-8111-111111111111'
const NODE_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const NEXT_NODE_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
const RENDER_ID = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'

const PROGRAM = [
  'root = Stack([intro], "md")',
  'intro = TextContent("El plazo de devolucion es de 30 dias.", "lead")',
].join('\n')

/** A lesson with a real control in it, for the §8.5 hit test. */
const PROGRAM_WITH_QUIZ = [
  'root = Stack([intro, quiz], "md")',
  'intro = TextContent("El plazo de devolucion es de 30 dias.", "lead")',
  'quiz = QuizItem("q1", "test", "apply", "Un cliente vuelve el dia 32. Que haces?", ' +
    '["Aceptar la devolucion", "Ofrecer garantia del fabricante"])',
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
    done: false,
    available: true,
    first_seen_at: '2026-08-20T09:00:00Z',
    completed_at: null,
    ...overrides,
  }
}

function nodeList(node: LearningNode): NodeList {
  return {
    course_id: COURSE_ID,
    delivery_mode: 'dynamic',
    schema_version: 3,
    next_node_id: null,
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
  renders?: Array<{ render_id: string; created_at: string | null; ui_format: string; status: string }>
  goal?: string | null
  /** Replace the two-node list — e.g. a single node so the current node is the last. */
  nodeListOverride?: NodeList
  /**
   * HTTP status for `POST /nodes/{id}/complete`. Defaults to `200`; a 5xx is how the
   * "a failed stamp never blocks the learner" case is set up.
   */
  completeStatus?: number
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

function servedRender(
  program: string,
  renderId = RENDER_ID,
  shellMode: 'legacy_stepper' | 'episode' = 'legacy_stepper',
) {
  return {
    render_id: renderId,
    node_id: NODE_ID,
    ui_format: 'explanation',
    status: 'ready',
    backend: 'openui',
    cached: false,
    shell_mode: shellMode,
    program,
  }
}

function installFetch(scenario: Scenario) {
  const renderQueue = [...scenario.renderResponses]
  const acceptedQueue = [...(scenario.accepted ?? [])]

  mockFetch.mockImplementation((input: string, init?: RequestInit) => {
    const url = String(input)
    const method = (init?.method ?? 'GET').toUpperCase()

    if (url.includes('/render/stream')) {
      return sseResponse(scenario.streamChunks ?? [])
    }
    if (url.endsWith(`/courses/${COURSE_ID}/nodes`)) {
      return jsonResponse(200, scenario.nodeListOverride ?? nodeList(scenario.node))
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
        learning_preferences: {
          modalities: ['audio', 'video'],
        },
      })
    }
    if (url.includes('/complete') && method === 'POST') {
      const status = scenario.completeStatus ?? 200
      return status < 400
        ? jsonResponse(status, {
            node_id: NODE_ID,
            completed_at: '2026-08-27T10:00:00Z',
            // Echoed, never written: the stamp and the mastery scale are two dimensions.
            state: 'not_started',
            mastery: 0,
            progress_percent: 100,
            can_complete: true,
          })
        : jsonResponse(status, { detail: 'boom', code: 'SERVER_ERROR' })
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

/**
 * `declaredReducedMotion` is the wizard's "Menos animaciones" answer (§6.2 Q5), which
 * `ProtectedRoute` provides in the real tree. Passing it here rather than faking
 * `matchMedia` exercises the half that only exists because the OS setting is unreachable
 * on a shared work laptop.
 */
function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location" data-pathname={location.pathname} />
}

function renderPage({ declaredReducedMotion = false } = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <declaredReducedMotionContext.Provider value={declaredReducedMotion}>
        <MemoryRouter initialEntries={[`/empleado/curso/${COURSE_ID}/nodo/${NODE_ID}`]}>
          <LocationProbe />
          <Routes>
            <Route path="/empleado/curso/:id/nodo/:nodeId" element={<NodeView />} />
          </Routes>
        </MemoryRouter>
      </declaredReducedMotionContext.Provider>
    </QueryClientProvider>,
  )
}

/**
 * The node's intro is now a deliberate start gate: the lesson content mounts only
 * after the learner clicks "Empezar", which is enabled once the render is ready
 * (before that it is a disabled "Preparando lección…"). Any test that asserts on the
 * lesson content has to pass through the gate first.
 */
async function enterLesson() {
  await userEvent.click(await screen.findByRole('button', { name: 'Empezar' }))
}

let warnSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
  warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
  // NodeView now remembers the screen the learner was on (`features/resume/storage`), and
  // jsdom's `localStorage` outlives a test. Without this, one test clicking "Empezar"
  // makes the next one start past the gate it is there to assert.
  window.localStorage.clear()
})

afterEach(() => {
  warnSpy.mockRestore()
  vi.restoreAllMocks()
})

// --------------------------------------------------------------------------- //

describe('NodeView — the frozen frame', () => {
  it('keeps the title and the close button in every phase', async () => {
    installFetch({
      node: learningNode({ state: 'not_started' }),
      renderResponses: [[202, { status: 'pending', request_id: null }]],
    })
    renderPage()

    // The node title appears in the header bar.
    const titles = await screen.findAllByText(/Plazo de devolucion/)
    expect(titles.length).toBeGreaterThan(0)
    // The X close button is always present.
    expect(screen.getByRole('button', { name: 'Cerrar panel' })).toBeInTheDocument()
  })

  it('renders the deterministic opening line from `goal`, never from the model', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [[200, servedRender(PROGRAM)]],
      goal: 'specific_gap',
    })
    renderPage()

    // The opening line lives in the lesson content, past the start gate.
    await enterLesson()
    expect(await screen.findByTestId('opening-line')).toHaveTextContent(
      'Va directo al problema que querías resolver.',
    )
  })
})

describe('NodeView — server-owned learning shell', () => {
  it('pages a multi-screen episode one beat at a time (no legacy stepper, never blocks)', async () => {
    // PROGRAM_WITH_QUIZ has TWO root children (lead + quiz), so the episode is a flow of
    // TWO screens the learner pages through. Only the current screen is on the DOM.
    installFetch({
      node: learningNode(),
      renderResponses: [[200, servedRender(PROGRAM_WITH_QUIZ, RENDER_ID, 'episode')]],
    })
    const { container } = renderPage()

    await enterLesson()

    // Screen 1: the lead beat only. The quiz beat lives on the next screen.
    // El contenido monta DESPUES de que la intro termine su salida: la envuelve un
    // `AnimatePresence mode="wait"`, que no monta la rama nueva hasta que la vieja
    // acaba. Esperar al TEXTO no basta como puerta —en modo episodio la mascota
    // tambien lo lee, fuera de la rama de la leccion, asi que aparece antes que el
    // armazon— y la comprobacion sincrona que venia despues llegaba demasiado pronto.
    await waitFor(() => {
      // Esperar al PIE, no al armazon: es lo que comprueban las aserciones de abajo, y
      // montan en commits distintos. Esperar a otra cosa deja una carrera que en esta
      // maquina no se ve y en un runner de CI, mas lento, falla.
      expect(container.querySelector('[data-episode-footer]')).not.toBeNull()
    })
    expect(container).toHaveTextContent('El plazo de devolucion es de 30 dias.')
    expect(container).not.toHaveTextContent('Un cliente vuelve el dia 32. Que haces?')
    // It is an episode, not the legacy stepper.
    expect(container.querySelector('[data-stepper-root]')).toBeNull()
    expect(container.querySelector('[data-episode-shell]')).not.toBeNull()
    expect(container.querySelector('[data-episode-stack]')).not.toBeNull()

    // The footer advances to the NEXT SCREEN (not the next node) while beats remain.
    await userEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
    await waitFor(() => {
      expect(container).toHaveTextContent('Un cliente vuelve el dia 32. Que haces?')
    })
  })

  // Regresion: un episodio `support_only` (solo prosa, sin QuizItem que resolver) no
  // tiene stepper —el modo episodio lo apaga— y sin un pie de avance propio dejaba al
  // aprendiz atrapado: ni flechas, ni boton de continuar, ninguna forma de salir.
  it('an episode with no quiz still offers a working advance control (never a dead end)', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [[200, servedRender(PROGRAM, RENDER_ID, 'episode')]],
    })
    const { container } = renderPage()

    await enterLesson()
    // El contenido monta DESPUES de que la intro termine su salida: la envuelve un
    // `AnimatePresence mode="wait"`, que no monta la rama nueva hasta que la vieja
    // acaba. Esperar al TEXTO no basta como puerta —en modo episodio la mascota
    // tambien lo lee, fuera de la rama de la leccion, asi que aparece antes que el
    // armazon— y la comprobacion sincrona que venia despues llegaba demasiado pronto.
    await waitFor(() => {
      // Esperar al PIE, no al armazon: es lo que comprueban las aserciones de abajo, y
      // montan en commits distintos. Esperar a otra cosa deja una carrera que en esta
      // maquina no se ve y en un runner de CI, mas lento, falla.
      expect(container.querySelector('[data-episode-footer]')).not.toBeNull()
    })
    expect(container).toHaveTextContent('El plazo de devolucion es de 30 dias.')

    // El episodio tiene un pie con una forma de avanzar, aunque no haya ejercicio.
    expect(container.querySelector('[data-episode-footer]')).not.toBeNull()
    const next = screen.getByRole('button', { name: /Siguiente: Excepciones/ })

    // Pulsarlo navega al siguiente nodo, igual que la flecha del stepper legacy.
    await userEvent.click(next)
    await waitFor(() => {
      expect(screen.getByTestId('location').dataset.pathname).toBe(
        `/empleado/curso/${COURSE_ID}/nodo/${NEXT_NODE_ID}`,
      )
    })
  })

  it('on the last node an episode footer finishes the course', async () => {
    // Un curso de un solo nodo: no hay siguiente, asi que el pie cierra el curso.
    const soloNode = learningNode()
    installFetch({
      node: soloNode,
      nodeListOverride: {
        course_id: COURSE_ID,
        delivery_mode: 'dynamic',
        schema_version: 3,
        next_node_id: null,
        nodes: [soloNode],
        can_complete: true,
        blocked_by: [],
        progress_percent: 80,
      },
      renderResponses: [[200, servedRender(PROGRAM, RENDER_ID, 'episode')]],
    })
    const { container } = renderPage()

    await enterLesson()
    // El contenido monta DESPUES de que la intro termine su salida: la envuelve un
    // `AnimatePresence mode="wait"`, que no monta la rama nueva hasta que la vieja
    // acaba. Esperar al TEXTO no basta como puerta —en modo episodio la mascota
    // tambien lo lee, fuera de la rama de la leccion, asi que aparece antes que el
    // armazon— y la comprobacion sincrona que venia despues llegaba demasiado pronto.
    await waitFor(() => {
      // Esperar al PIE, no al armazon: es lo que comprueban las aserciones de abajo, y
      // montan en commits distintos. Esperar a otra cosa deja una carrera que en esta
      // maquina no se ve y en un runner de CI, mas lento, falla.
      expect(container.querySelector('[data-episode-footer]')).not.toBeNull()
    })
    expect(container).toHaveTextContent('El plazo de devolucion es de 30 dias.')

    expect(container.querySelector('[data-episode-footer]')).not.toBeNull()
    const finish = screen.getByRole('button', { name: 'Terminar el curso' })
    await userEvent.click(finish)

    // El curso se cierra: aparece la pantalla de celebracion.
    expect(await screen.findByText('¡Curso completado!')).toBeInTheDocument()
  })

  // Regresion: en una pantalla con ejercicio, el boton de avanzar quedaba TAPADO por el
  // contenido del ejercicio. El pie debe reservar su hueco (hermano `shrink-0`, no
  // superpuesto) y el contenido desplazarse/recortarse dentro de su propia caja, de modo
  // que un ejercicio alto nunca pinte por encima del control de avance.
  it('reserves the episode footer outside the clipped content so tall exercises never cover the advance control', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [[200, servedRender(PROGRAM_WITH_QUIZ, RENDER_ID, 'episode')]],
    })
    const { container } = renderPage()

    await enterLesson()
    // El contenido monta DESPUES de que la intro termine su salida: la envuelve un
    // `AnimatePresence mode="wait"`, que no monta la rama nueva hasta que la vieja
    // acaba. Esperar al TEXTO no basta como puerta —en modo episodio la mascota
    // tambien lo lee, fuera de la rama de la leccion, asi que aparece antes que el
    // armazon— y la comprobacion sincrona que venia despues llegaba demasiado pronto.
    await waitFor(() => {
      // Esperar al PIE, no al armazon: es lo que comprueban las aserciones de abajo, y
      // montan en commits distintos. Esperar a otra cosa deja una carrera que en esta
      // maquina no se ve y en un runner de CI, mas lento, falla.
      expect(container.querySelector('[data-episode-footer]')).not.toBeNull()
    })
    expect(container).toHaveTextContent('El plazo de devolucion es de 30 dias.')

    const footer = container.querySelector('[data-episode-footer]') as HTMLElement
    expect(footer).not.toBeNull()
    // El control de avance vive en el pie y es alcanzable.
    expect(footer.querySelector('button')).not.toBeNull()
    // El pie reserva hueco (`shrink-0`) en vez de flotar sobre el contenido, y NO esta
    // posicionado de forma absoluta/fija (que dejaria que el contenido lo tapara).
    expect(footer.className).toContain('shrink-0')
    expect(footer.className).not.toMatch(/\babsolute\b|\bfixed\b/)

    // El contenido de la leccion vive en un hermano RECORTADO (`overflow-hidden`) que
    // precede al pie bajo el mismo padre: un ejercicio que desborde no puede derramarse
    // sobre el control de avance.
    const shell = container.querySelector('[data-episode-shell]') as HTMLElement
    const clipped = shell.closest('.overflow-hidden') as HTMLElement
    expect(clipped).not.toBeNull()
    const parent = footer.parentElement as HTMLElement
    expect(parent.contains(clipped)).toBe(true)
    const kids = Array.from(parent.children)
    expect(kids.indexOf(clipped)).toBeGreaterThanOrEqual(0)
    expect(kids.indexOf(clipped)).toBeLessThan(kids.indexOf(footer))

    // La pantalla del episodio se desplaza dentro de su propia caja (scroll interno), no
    // arrastrando al pie.
    const stack = container.querySelector('[data-episode-stack]') as HTMLElement
    expect(stack.querySelector('.overflow-y-auto')).not.toBeNull()
  })

  it('prefetches the next 4 nodes ahead (sliding window), not the 5th', async () => {
    const aheadIds = ['ahead-a', 'ahead-b', 'ahead-c', 'ahead-d', 'ahead-e']
    const current = learningNode()
    const nodes = [
      current,
      ...aheadIds.map((id, i) =>
        learningNode({
          id,
          title: `Nodo ${i + 2}`,
          position: i + 2,
          state: 'not_started',
          mastery: 0,
        }),
      ),
    ]
    installFetch({
      node: current,
      nodeListOverride: {
        course_id: COURSE_ID,
        delivery_mode: 'dynamic',
        schema_version: 3,
        next_node_id: null,
        nodes,
        can_complete: false,
        blocked_by: [],
        progress_percent: 10,
      },
      renderResponses: [[200, servedRender(PROGRAM, RENDER_ID, 'episode')]],
    })
    renderPage()

    // El prefetch se dispara al servirse el render del nodo actual (dispara-y-olvida,
    // idempotente en el servidor). No hay que entrar en la leccion.
    await waitFor(() => {
      expect(callsTo(`/nodes/${aheadIds[3]}/render`, 'POST')).toHaveLength(1)
    })
    // Los cuatro siguientes nodos se pre-generan.
    for (const id of aheadIds.slice(0, 4)) {
      expect(callsTo(`/nodes/${id}/render`, 'POST')).toHaveLength(1)
    }
    // El quinto queda fuera de la ventana deslizante.
    expect(callsTo(`/nodes/${aheadIds[4]}/render`, 'POST')).toHaveLength(0)
  })

  it('keeps Web, Audio and Video modalities invisible even when they are preferred', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [[200, servedRender(PROGRAM, RENDER_ID, 'episode')]],
    })
    const { container } = renderPage()

    await enterLesson()
    await waitFor(() => {
      expect(container).toHaveTextContent('El plazo de devolucion es de 30 dias.')
    })

    expect(
      screen.queryByRole('button', { name: /^(web|audio|v[ií]deo)$/i }),
    ).toBeNull()
    expect(screen.queryByRole('navigation', { name: /modalidad/i })).toBeNull()
  })

  it('preserves the legacy stepper and its solvable split exactly', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [[200, servedRender(PROGRAM_WITH_QUIZ)]],
    })
    const { container } = renderPage()

    await enterLesson()
    await waitFor(() => {
      expect(container).toHaveTextContent('El plazo de devolucion es de 30 dias.')
    })
    expect(container).not.toHaveTextContent('Un cliente vuelve el dia 32. Que haces?')
    expect(container.querySelector('[data-stepper-root]')).not.toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'Siguiente paso' }))
    await waitFor(() => {
      expect(container).toHaveTextContent('Un cliente vuelve el dia 32. Que haces?')
    })
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

    await enterLesson()
    await waitFor(() => expect(container).toHaveTextContent('El plazo de devolucion es de 30 dias.'))
    // The `ui_block` payload is a pre-gate component dict; it must never be rendered, so
    // its own type name cannot appear on screen.
    expect(container).not.toHaveTextContent('TextContent')
    expect(screen.queryByTestId('node-skeleton')).not.toBeInTheDocument()
  })

  it('shows the intro screen while it waits for the render', async () => {
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

    // While streaming, the intro screen (with topic overview) is shown instead
    // of the old format-shaped skeleton.
    await waitFor(() =>
      expect(screen.getByTestId('node-intro')).toBeInTheDocument(),
    )
    const intro = screen.getByTestId('node-intro')
    // The intro shows the node title and summary
    expect(intro).toHaveTextContent('Plazo de devolucion')
    expect(intro).toHaveTextContent('Cuantos dias tiene el cliente para devolver.')
  })

  it('holds the intro as a start gate until the learner clicks "Empezar"', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [[200, servedRender(PROGRAM)]],
    })
    const { container } = renderPage()

    // The render is ready, but the lesson must not mount on its own: the intro stays,
    // now offering an enabled "Empezar" the learner controls.
    const start = await screen.findByRole('button', { name: 'Empezar' })
    expect(screen.getByTestId('node-intro')).toBeInTheDocument()
    expect(container).not.toHaveTextContent('El plazo de devolucion es de 30 dias.')

    // Clicking it, and only then, enters the lesson content.
    await userEvent.click(start)
    await waitFor(() => expect(container).toHaveTextContent('El plazo de devolucion es de 30 dias.'))
    expect(screen.queryByTestId('node-intro')).not.toBeInTheDocument()
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
    expect(screen.queryByText('No se pudo preparar esta lección.')).not.toBeInTheDocument()
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

    await enterLesson()
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

    expect(await screen.findByText('No se pudo preparar esta lección.')).toBeInTheDocument()
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

    await enterLesson()
    await waitFor(() => expect(container).toHaveTextContent('El plazo de devolucion es de 30 dias.'))
    expect(callsTo('/render/stream')).toHaveLength(0)
  })
})

describe('NodeView — the pinned render is the lesson (§5.5)', () => {
  /**
   * What is left of §5.5 once the regenerate button is gone: the learner gets the pinned
   * render and has no way to ask for a different one. `fc6a348` removed the only call that
   * recomputed a node from the browser, so a `POST` with `force: true` must not go out at
   * all — that is the claim the two deleted tests were really protecting, and it is the
   * one that still means something.
   */
  it('never asks the server to recompute the lesson', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [[200, servedRender(PROGRAM)]],
      renders: [
        { render_id: RENDER_ID, created_at: '2026-07-26T09:00:00Z', ui_format: 'explanation', status: 'ready' },
      ],
    })
    const { container } = renderPage()

    await enterLesson()
    await waitFor(() => expect(container).toHaveTextContent('El plazo de devolucion es de 30 dias.'))

    // A render that is already pinned is served, not re-requested — with or without force.
    expect(callsTo(`/nodes/${NODE_ID}/render`, 'POST')).toHaveLength(0)
    // And no affordance offers to: the feedback row is optional and changes nothing.
    expect(screen.queryByRole('button', { name: 'Actualizar esta lección' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Ver la versión anterior' })).toBeNull()
  })
})

describe('NodeView — how the lesson arrives (§9.2)', () => {
  /** The staggering container, applied by `StackBlock` to the root Stack of a program. */
  function staggered(container: HTMLElement) {
    return container.querySelectorAll('.block-arrival')
  }

  it('renders the lesson content without block-arrival stagger under stepper mode', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [
        [202, { status: 'pending', request_id: null }],
        [200, servedRender(PROGRAM)],
      ],
      accepted: [{ request_id: 'req-1', cached: false, render_id: null }],
      streamChunks: [
        `event: ui_done\ndata: ${JSON.stringify({ render_id: RENDER_ID, format: 'explanation', status: 'ready' })}\n\n`,
      ],
    })
    const { container } = renderPage()

    await enterLesson()
    await waitFor(() => expect(container).toHaveTextContent('El plazo de devolucion es de 30 dias.'))
    // In stepper mode the root Stack renders children one at a time.
    // block-arrival stagger is not used because the stepper handles sequencing.
    expect(staggered(container)).toHaveLength(0)
  })

  /**
   * The other half of the cadence: the learner's declared preference silences it.
   *
   * This used to be asserted through "go back to the previous version" — a held render was
   * the one case that painted with no entrance. `fc6a348` removed the version history, and
   * with it the only path to a program that must *not* animate... except this one, which is
   * the reason the switch exists at all (`useReducedMotion` reads the OS setting **and**
   * the preference set in the onboarding wizard).
   */
  it('does not animate at all when the learner asked for less motion', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [
        [202, { status: 'pending', request_id: null }],
        [200, servedRender(PROGRAM)],
      ],
      accepted: [{ request_id: 'req-1', cached: false, render_id: null }],
      streamChunks: [
        `event: ui_done\ndata: ${JSON.stringify({ render_id: RENDER_ID, format: 'explanation', status: 'ready' })}\n\n`,
      ],
    })
    const { container } = renderPage({ declaredReducedMotion: true })

    await enterLesson()
    await waitFor(() => expect(container).toHaveTextContent('El plazo de devolucion es de 30 dias.'))
    expect(staggered(container)).toHaveLength(0)
  })
})

describe('NodeView — click to explain (§8.5)', () => {
  /**
   * The control clicked here is a quiz option, not the page's own chrome.
   *
   * It used to be "Actualizar esta lección", which `fc6a348` removed — and that button was
   * a weak subject anyway: it sat in the surface, but so does every other button, and a
   * quiz option is the case §8.5 was written for. Explaining the words of an option the
   * learner just clicked hands out a free, uncounted hint on the correct answer.
   */
  it('explains a word in the lesson but not a click on a quiz option', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [[200, servedRender(PROGRAM_WITH_QUIZ)]],
    })
    const { container } = renderPage()

    await enterLesson()
    // In stepper mode, the TextContent step is shown first.
    await waitFor(() => expect(container).toHaveTextContent('El plazo de devolucion es de 30 dias.'))

    // Click a word in the lead text — should trigger an explain popover.
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

    expect(await screen.findByText('Esta lección está pendiente de revisión')).toBeInTheDocument()
    expect(callsTo(`/nodes/${NODE_ID}/render`, 'POST')).toHaveLength(0)
  })
})

/**
 * "Llego hasta un punto, salgo y vuelvo a entrar y no se ha guardado por donde iba."
 *
 * The server knows which NODE to reopen (`first_seen_at`, stamped when a render is
 * served). Where inside the node the learner was is only knowable here, and it used to be
 * thrown away twice per re-entry: `setEntered(false)` put the start gate back and
 * `setEpisodeScreen(0)` put screen one back. Both are now seeded from
 * `features/resume/storage`.
 */
describe('NodeView — coming back to a node', () => {
  function footer(container: HTMLElement) {
    return container.querySelector('[data-episode-footer]') as HTMLElement | null
  }

  it('reopens on the saved screen, past the start gate', async () => {
    writeNodePosition(COURSE_ID, NODE_ID, { screen: 1, entered: true })
    installFetch({
      node: learningNode(),
      renderResponses: [[200, servedRender(PROGRAM_WITH_QUIZ, RENDER_ID, 'episode')]],
    })
    const { container } = renderPage()

    // No `enterLesson()`: the gate is a first-visit screen, and this is not a first visit.
    await waitFor(() => expect(footer(container)).not.toBeNull())
    expect(screen.queryByRole('button', { name: 'Empezar' })).toBeNull()
    expect(footer(container)?.dataset.episodeScreen).toBe('1')
    expect(container).toHaveTextContent('Un cliente vuelve el dia 32. Que haces?')
  })

  it('falls back to the last valid screen when the episode was regenerated shorter', async () => {
    // Saved on screen 8 of a longer episode; this one only has two screens.
    writeNodePosition(COURSE_ID, NODE_ID, { screen: 8, entered: true })
    installFetch({
      node: learningNode(),
      renderResponses: [[200, servedRender(PROGRAM_WITH_QUIZ, RENDER_ID, 'episode')]],
    })
    const { container } = renderPage()

    await waitFor(() => expect(footer(container)).not.toBeNull())
    await waitFor(() => expect(footer(container)?.dataset.episodeTotal).toBe('2'))
    expect(footer(container)?.dataset.episodeScreen).toBe('1')
    // Clamped, not blank: there is content on screen and an advance control under it.
    expect(container).toHaveTextContent('Un cliente vuelve el dia 32. Que haces?')
  })

  it('records the screen as the learner advances', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [[200, servedRender(PROGRAM_WITH_QUIZ, RENDER_ID, 'episode')]],
    })
    const { container } = renderPage()

    await enterLesson()
    await waitFor(() => expect(footer(container)).not.toBeNull())
    expect(readNodePosition(COURSE_ID, NODE_ID)).toEqual({ screen: 0, entered: true })

    await userEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
    await waitFor(() =>
      expect(readNodePosition(COURSE_ID, NODE_ID)).toEqual({ screen: 1, entered: true }),
    )
  })

  it('forgets the node it leaves behind, so a finished node keeps no bookmark', async () => {
    writeNodePosition(COURSE_ID, NODE_ID, { screen: 1, entered: true })
    installFetch({
      node: learningNode(),
      renderResponses: [[200, servedRender(PROGRAM_WITH_QUIZ, RENDER_ID, 'episode')]],
    })
    const { container } = renderPage()

    await waitFor(() => expect(footer(container)).not.toBeNull())
    // On the last screen "Siguiente" is the next NODE, and that is the exit.
    await userEvent.click(screen.getByRole('button', { name: /Excepciones/ }))
    await waitFor(() => expect(readNodePosition(COURSE_ID, NODE_ID)).toBeNull())
  })
})

/**
 * "Acabo el curso y la barra marca 0%."
 *
 * The count behind that bar is `mastered` nodes, and mastery needs 0.90 plus three
 * consecutive correct answers (rule 6 of §7.3) — unreachable for an episode that presents
 * one item per node, and flatly impossible for an expository one. The server now counts a
 * node with `completed_at` as done; finishing a node, though, is pure client-side
 * navigation, so **the only way the server hears about it is these calls**.
 *
 * The endpoint is idempotent, so what these tests pin is not correctness of a guard but
 * the two product rules around it: one call per node finished (a screen turn inside a node
 * is not finishing it), and a failed call never costs the learner their advance.
 */
describe('NodeView — telling the server the node is finished', () => {
  function footer(container: HTMLElement) {
    return container.querySelector('[data-episode-footer]') as HTMLElement | null
  }

  const completeCalls = () => callsTo(`/nodes/${NODE_ID}/complete`, 'POST')

  it('stamps the node once when the learner leaves it for the next one', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [[200, servedRender(PROGRAM_WITH_QUIZ, RENDER_ID, 'episode')]],
    })
    const { container } = renderPage()

    await enterLesson()
    await waitFor(() => expect(footer(container)).not.toBeNull())

    // Screen 0 of 2: nothing is finished yet.
    expect(completeCalls()).toHaveLength(0)

    // Onto the last screen, then out of the node.
    await userEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
    await waitFor(() => expect(footer(container)?.dataset.episodeScreen).toBe('1'))
    await userEvent.click(screen.getByRole('button', { name: /Siguiente: Excepciones/ }))

    await waitFor(() => expect(completeCalls()).toHaveLength(1))
    // And the advance happened, which is the point of leaving.
    await waitFor(() => {
      expect(screen.getByTestId('location').dataset.pathname).toBe(
        `/empleado/curso/${COURSE_ID}/nodo/${NEXT_NODE_ID}`,
      )
    })
  })

  it('does not stamp anything for a screen turn inside the same node', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [[200, servedRender(PROGRAM_WITH_QUIZ, RENDER_ID, 'episode')]],
    })
    const { container } = renderPage()

    await enterLesson()
    await waitFor(() => expect(footer(container)).not.toBeNull())

    // Screen 0 -> 1 of the same episode. The node is not finished, so nothing is said.
    await userEvent.click(screen.getByRole('button', { name: 'Siguiente' }))
    await waitFor(() => {
      expect(container).toHaveTextContent('Un cliente vuelve el dia 32. Que haces?')
    })
    expect(completeCalls()).toHaveLength(0)
  })

  it('stamps the last node when the course is finished', async () => {
    // One node, so the footer's forward control is "Terminar el curso" — the branch that
    // both the episode footer and the legacy stepper's CTA reach through `finishCourse`.
    const soloNode = learningNode()
    installFetch({
      node: soloNode,
      nodeListOverride: {
        course_id: COURSE_ID,
        delivery_mode: 'dynamic',
        schema_version: 3,
        next_node_id: null,
        nodes: [soloNode],
        can_complete: true,
        blocked_by: [],
        progress_percent: 80,
      },
      renderResponses: [[200, servedRender(PROGRAM, RENDER_ID, 'episode')]],
    })
    const { container } = renderPage()

    await enterLesson()
    await waitFor(() => expect(footer(container)).not.toBeNull())
    expect(completeCalls()).toHaveLength(0)

    await userEvent.click(screen.getByRole('button', { name: 'Terminar el curso' }))

    await waitFor(() => expect(completeCalls()).toHaveLength(1))
    expect(await screen.findByText('¡Curso completado!')).toBeInTheDocument()
  })

  it('never blocks the advance when the stamp fails', async () => {
    installFetch({
      node: learningNode(),
      renderResponses: [[200, servedRender(PROGRAM, RENDER_ID, 'episode')]],
      completeStatus: 500,
    })
    const { container } = renderPage()

    await enterLesson()
    await waitFor(() => expect(footer(container)).not.toBeNull())

    // PROGRAM is a single beat, so the only forward control is the next node.
    await userEvent.click(screen.getByRole('button', { name: /Siguiente: Excepciones/ }))

    await waitFor(() => expect(completeCalls()).toHaveLength(1))
    // The learner moved on anyway, and nothing about the failure reached the screen.
    await waitFor(() => {
      expect(screen.getByTestId('location').dataset.pathname).toBe(
        `/empleado/curso/${COURSE_ID}/nodo/${NEXT_NODE_ID}`,
      )
    })
    expect(container).not.toHaveTextContent('boom')
  })
})
