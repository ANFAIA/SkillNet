import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { NodeView } from './NodeView'
import { declaredReducedMotionContext } from '../../hooks/useReducedMotion'
import type { LearningNode, NodeList } from '../../types'

/**
 * "Me quedé mirando 'Preparando lección…' para siempre."
 *
 * The lesson is announced over SSE, and that stream dies quietly in three ordinary
 * situations: a proxy that buffers `text/event-stream`, a dropped connection, a background
 * tab the browser throttles. None of them is a failed render — the graph keeps running and
 * `GET /render` still holds the answer — but none of them settles the stream either, so
 * nothing asked that question again: the render query pins its answer (`staleTime:
 * Infinity`, no refetch on focus) and the effect that arms a request bails out once a
 * `request_id` exists. Only a page reload moved the screen.
 *
 * What these two pin is the shape of the fix, not just its effect: the poll has to
 * **recover** and it has to **end**. An unbounded retry would trade one bug for a tab that
 * bills the server for ever, which is why the interval was off in the first place.
 *
 * ## Why this is its own file
 *
 * Both tests need fake timers to skip the two-minute budget, and faking `setTimeout`
 * **permanently breaks framer-motion for the rest of the file**: its frame loop looks the
 * global up at call time, so a frame scheduled while the clock is faked is thrown away
 * when the clock is uninstalled and nothing ever schedules the next one. Every later test
 * then hangs on an `AnimatePresence mode="wait"` exit that never completes. Vitest gives
 * each file its own environment, so the blast radius stops at this file — which contains
 * nothing that animates.
 */

const COURSE_ID = '11111111-1111-4111-8111-111111111111'
const NODE_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const RENDER_ID = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'

const PROGRAM = [
  'root = Stack([intro], "md")',
  'intro = TextContent("El plazo de devolucion es de 30 dias.", "lead")',
].join('\n')

/** One progress event and then silence: a stream cut before `ui_done`. */
const TRUNCATED_STREAM = [
  `event: render_step\ndata: ${JSON.stringify({ step: 'genera_ui', message: 'Escribiendo…' })}\n\n`,
]

const NODE: LearningNode = {
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
}

const NODE_LIST: NodeList = {
  course_id: COURSE_ID,
  delivery_mode: 'dynamic',
  schema_version: 3,
  next_node_id: null,
  nodes: [NODE],
  can_complete: false,
  blocked_by: [NODE_ID],
  progress_percent: 20,
}

const mockFetch = vi.fn()

function jsonResponse(status: number, body: unknown) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) })
}

/** A real SSE body: one `read()` per chunk, then `done`. */
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

function servedRender(program: string) {
  return {
    render_id: RENDER_ID,
    node_id: NODE_ID,
    ui_format: 'explanation',
    status: 'ready',
    backend: 'openui',
    cached: false,
    shell_mode: 'legacy_stepper',
    program,
  }
}

/** `renderResponses` is consumed in order by `GET /render`; the last entry repeats. */
function installFetch(renderResponses: Array<[number, unknown]>) {
  const queue = [...renderResponses]
  mockFetch.mockImplementation((input: string, init?: RequestInit) => {
    const url = String(input)
    const method = (init?.method ?? 'GET').toUpperCase()

    if (url.includes('/render/stream')) return sseResponse(TRUNCATED_STREAM)
    if (url.endsWith(`/courses/${COURSE_ID}/nodes`)) return jsonResponse(200, NODE_LIST)
    if (url.endsWith('/users/me/learner-profile')) return jsonResponse(404, { detail: 'none' })
    if (url.endsWith(`/nodes/${NODE_ID}/render`) && method === 'POST') {
      return jsonResponse(202, { request_id: 'req-1', cached: false, render_id: null })
    }
    if (url.endsWith(`/nodes/${NODE_ID}/render`) && method === 'GET') {
      const next = queue.length > 1 ? queue.shift() : queue[0]
      const [status, body] = next ?? [202, { status: 'pending', request_id: null }]
      return jsonResponse(status, body)
    }
    if (url.endsWith(`/nodes/${NODE_ID}/events`)) return jsonResponse(204, null)
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
      {/* Reduced motion: nothing here depends on an animation completing. */}
      <declaredReducedMotionContext.Provider value={true}>
        <MemoryRouter initialEntries={[`/empleado/curso/${COURSE_ID}/nodo/${NODE_ID}`]}>
          <Routes>
            <Route path="/empleado/curso/:id/nodo/:nodeId" element={<NodeView />} />
          </Routes>
        </MemoryRouter>
      </declaredReducedMotionContext.Provider>
    </QueryClientProvider>,
  )
}

let warnSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
  warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
  window.localStorage.clear()
  // Timer functions only. Faking `Date`/`performance` as well and then jumping minutes
  // forward moves other clocks backwards when real timers return.
  vi.useFakeTimers({
    shouldAdvanceTime: true,
    toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'],
  })
})

afterEach(() => {
  vi.useRealTimers()
  warnSpy.mockRestore()
  vi.restoreAllMocks()
})

describe('NodeView — a lesson that never arrives', () => {
  it('recovers by asking `GET /render` again when the stream dies without saying so', async () => {
    // Somebody's task owns the render, so the view subscribes instead of asking for a
    // second one. The next answer is the lesson — but only if anybody asks again.
    installFetch([
      [202, { status: 'generating', request_id: 'req-1' }],
      [200, servedRender(PROGRAM)],
    ])
    renderPage()

    // The start gate is where the bug lived: a disabled button and no way forward.
    expect(await screen.findByRole('button', { name: 'Preparando lección…' })).toBeDisabled()

    // Nobody touches anything. The bounded poll asks again and the lesson lands.
    await vi.advanceTimersByTimeAsync(5000)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Empezar' })).toBeEnabled()
    })
  })

  it('stops polling when the wait is spent, and offers a retry that asks again', async () => {
    // The render never arrives, however many times it is asked for.
    installFetch([[202, { status: 'generating', request_id: 'req-1' }]])
    renderPage()

    await screen.findByRole('button', { name: 'Preparando lección…' })

    // Two minutes of asking, and then the screen says so instead of lying.
    await vi.advanceTimersByTimeAsync(125_000)
    const panel = await screen.findByTestId('lesson-unavailable')
    expect(panel).toHaveTextContent('No se pudo preparar esta lección.')
    // And the dead end is gone: the gate that could never open is off the screen.
    expect(screen.queryByRole('button', { name: 'Preparando lección…' })).toBeNull()

    // Bounded: from here on nobody asks the server anything.
    const asked = callsTo(`/nodes/${NODE_ID}/render`, 'GET').length
    await vi.advanceTimersByTimeAsync(60_000)
    expect(callsTo(`/nodes/${NODE_ID}/render`, 'GET')).toHaveLength(asked)

    // The retry is a person deciding, once, that it is worth another wait.
    const requested = callsTo(`/nodes/${NODE_ID}/render`, 'POST').length
    fireEvent.click(screen.getByRole('button', { name: 'Reintentar' }))
    await waitFor(() => {
      expect(callsTo(`/nodes/${NODE_ID}/render`, 'POST').length).toBe(requested + 1)
    })
    // The message is gone and the clock is running again.
    await waitFor(() => expect(screen.queryByTestId('lesson-unavailable')).toBeNull())
    const resumed = callsTo(`/nodes/${NODE_ID}/render`, 'GET').length
    await vi.advanceTimersByTimeAsync(5000)
    await waitFor(() => {
      expect(callsTo(`/nodes/${NODE_ID}/render`, 'GET').length).toBeGreaterThan(resumed)
    })
  })
})
