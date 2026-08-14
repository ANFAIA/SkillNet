import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import {
  elementForFormat,
  isNodeNotReviewed,
  isNodeSurfaceDisabled,
  isPendingRender,
  isServedRender,
  useNodeRenderStream,
  useSubmitNodeAnswer,
} from './nodes'
import { ApiError } from './client'

/**
 * The SSE parser of the render stream, on its own (§12.3).
 *
 * It is tested apart from the screen because its whole job is to survive inputs a screen
 * test cannot express: a chunk boundary in the middle of a `data:` line, an `event:` with
 * no payload, a payload that is not JSON, and a connection that simply stops. The pub/sub
 * behind it is in-memory, single worker and keeps no backlog (§9.2), so every one of those
 * is a normal Tuesday, not an exotic failure.
 *
 * The contract the parser owes its caller: it **never throws**, it only reports `error`
 * when the server said `error`, and a truncated stream leaves the status on `streaming` so
 * the caller falls back to `GET /render` instead of showing a failure.
 */

const NODE_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const RENDER_ID = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'

const mockFetch = vi.fn()

/** One `read()` per chunk, so a chunk list *is* a byte-level truncation scenario. */
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

function event(type: string, data: unknown) {
  return `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`
}

function install(chunks: string[]) {
  mockFetch.mockImplementation(() => sseResponse(chunks))
}

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useNodeRenderStream', () => {
  it('reports the step, the format, every block and the final render id', async () => {
    install([
      event('render_step', { step: 'decide_formato', message: 'Eligiendo la forma de la leccion...' }),
      event('ui_format', { format: 'chart', tier: 'heavy' }),
      event('ui_block', { component: { id: 'b0', type: 'Stack' } }),
      event('ui_block', { component: { id: 'b1', type: 'Chart' } }),
      event('ui_done', { render_id: RENDER_ID, format: 'chart', status: 'ready' }),
    ])

    const settled: unknown[] = []
    const { result } = renderHook(() =>
      useNodeRenderStream({ onSettled: (outcome) => settled.push(outcome) }),
    )

    await act(async () => {
      await result.current.start(NODE_ID, 'req-1')
    })

    await waitFor(() => expect(result.current.status).toBe('done'))
    expect(result.current.step).toBe('decide_formato')
    expect(result.current.message).toBe('Eligiendo la forma de la leccion...')
    expect(result.current.format).toBe('chart')
    expect(result.current.blocks).toBe(2)
    expect(result.current.renderId).toBe(RENDER_ID)
    expect(settled).toEqual([{ reason: 'done', renderId: RENDER_ID, fallbackAvailable: false }])
  })

  it('counts `ui_block` incrementally, one chunk at a time', async () => {
    // Split so a single event arrives across two reads: the `data:` line is completed by
    // the following chunk, which is the case a naive line parser drops.
    install([
      'event: ui_block\ndata: {"component": {"id": "b0", ',
      '"type": "TextContent"}}\n\n',
      event('ui_block', { component: { id: 'b1', type: 'Callout' } }),
    ])

    const { result } = renderHook(() => useNodeRenderStream())
    await act(async () => {
      await result.current.start(NODE_ID, 'req-1')
    })

    await waitFor(() => expect(result.current.blocks).toBe(2))
    // No terminal event arrived, so this is still an open render as far as the caller is
    // concerned — not a failure.
    expect(result.current.status).toBe('streaming')
    expect(result.current.error).toBeNull()
  })

  it('surfaces `error` with `fallback: true` as a recoverable outcome', async () => {
    install([
      event('error', { step: 'genera_ui', message: 'El modelo no respondio', fallback: true }),
    ])

    const settled: Array<{ reason: string; fallbackAvailable: boolean }> = []
    const { result } = renderHook(() =>
      useNodeRenderStream({ onSettled: (outcome) => settled.push(outcome) }),
    )
    await act(async () => {
      await result.current.start(NODE_ID, 'req-1')
    })

    await waitFor(() => expect(result.current.status).toBe('error'))
    expect(result.current.error).toBe('El modelo no respondio')
    expect(result.current.fallbackAvailable).toBe(true)
    expect(settled).toEqual([{ reason: 'error', renderId: null, fallbackAvailable: true }])
  })

  it('marks `error` with `fallback: false` as nothing left to serve', async () => {
    install([event('error', { step: 'validate_ui', message: 'Sin contenido', fallback: false })])

    const { result } = renderHook(() => useNodeRenderStream())
    await act(async () => {
      await result.current.start(NODE_ID, 'req-1')
    })

    await waitFor(() => expect(result.current.fallbackAvailable).toBe(false))
    expect(result.current.status).toBe('error')
  })

  it('reports `node_skipped` as its own terminal state', async () => {
    install([event('node_skipped', { reason: 'mastered' })])

    const { result } = renderHook(() => useNodeRenderStream())
    await act(async () => {
      await result.current.start(NODE_ID, 'req-1')
    })

    await waitFor(() => expect(result.current.skipped).toBe(true))
    expect(result.current.status).toBe('skipped')
  })

  it('ignores a data line that is not JSON and keeps going', async () => {
    install([
      'event: ui_block\ndata: {"component": broken\n\n',
      event('ui_done', { render_id: RENDER_ID, format: 'explanation', status: 'ready' }),
    ])

    const { result } = renderHook(() => useNodeRenderStream())
    await act(async () => {
      await result.current.start(NODE_ID, 'req-1')
    })

    await waitFor(() => expect(result.current.status).toBe('done'))
    expect(result.current.blocks).toBe(0)
  })

  it('stays on `streaming` when the connection dies mid-event', async () => {
    install([event('ui_format', { format: 'explanation', tier: 'fast' }), 'event: ui_do'])

    const settled: unknown[] = []
    const { result } = renderHook(() =>
      useNodeRenderStream({ onSettled: (outcome) => settled.push(outcome) }),
    )
    await act(async () => {
      await result.current.start(NODE_ID, 'req-1')
    })

    expect(result.current.status).toBe('streaming')
    expect(result.current.format).toBe('explanation')
    // Nothing settled: a cut stream must not be reported as a finished render, or the
    // caller would stop asking `GET /render` for content that is still coming.
    expect(settled).toEqual([])
  })

  it('does not fail when the stream endpoint refuses the subscription', async () => {
    mockFetch.mockImplementation(() =>
      Promise.resolve({ ok: false, status: 404, body: null, json: () => Promise.resolve({}) }),
    )

    const { result } = renderHook(() => useNodeRenderStream())
    await act(async () => {
      await result.current.start(NODE_ID, 'req-1')
    })

    // The render may still be running server-side; `GET /render` decides, not this.
    expect(result.current.status).toBe('streaming')
    expect(result.current.error).toBeNull()
  })

  it('refuses to open a stream without a request id', async () => {
    install([event('ui_done', { render_id: RENDER_ID, format: 'explanation', status: 'ready' })])

    const { result } = renderHook(() => useNodeRenderStream())
    await act(async () => {
      await result.current.start(NODE_ID, '')
    })

    // An empty `request_id` is the `cached: true` answer of `POST /render`: there is no
    // channel and nobody will ever publish to it.
    expect(mockFetch).not.toHaveBeenCalled()
    expect(result.current.status).toBe('idle')
  })

  it('sends the request id as a query parameter, url-encoded', async () => {
    install([event('ui_done', { render_id: RENDER_ID, format: 'explanation', status: 'ready' })])

    const { result } = renderHook(() => useNodeRenderStream())
    await act(async () => {
      await result.current.start(NODE_ID, 'req 1&x')
    })

    expect(String(mockFetch.mock.calls[0][0])).toBe(
      `/api/v1/nodes/${NODE_ID}/render/stream?request_id=req%201%26x`,
    )
  })
})

describe('useSubmitNodeAnswer', () => {
  it('always reports `hints_used: 0`, because the client cannot be the one to count', async () => {
    mockFetch.mockImplementation(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            score: 1,
            passed: true,
            feedback: null,
            correct_answer: { selected: 2 },
            mastery: 0.7,
            state: 'learning',
            consecutive_correct: 1,
            consecutive_failed: 0,
            next: 'next_item',
            show_worked_solution: false,
          }),
      }),
    )

    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
    const wrapper = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client }, children)

    const { result } = renderHook(() => useSubmitNodeAnswer(NODE_ID), { wrapper })
    await act(async () => {
      await result.current.mutateAsync({
        render_id: RENDER_ID,
        item_id: 'q1',
        answer: { selected: 2 },
        latency_ms: 4200,
      })
    })

    const body = JSON.parse(String((mockFetch.mock.calls[0][1] as RequestInit).body))
    // The number that decides whether `correct_answer` is revealed is derived server-side
    // from `node_attempts.hints_used` (§11.3). Sending anything but 0 from here would be
    // offering the server a free answer key, so the hook does not take the field at all.
    expect(body).toEqual({
      render_id: RENDER_ID,
      item_id: 'q1',
      answer: { selected: 2 },
      latency_ms: 4200,
      hints_used: 0,
    })
  })
})

describe('render response narrowing', () => {
  const served = {
    render_id: RENDER_ID,
    node_id: NODE_ID,
    ui_format: 'explanation' as const,
    status: 'ready' as const,
    backend: 'openui',
    cached: false,
    shell_mode: 'legacy_stepper' as const,
    program: 'root = Stack([a], "md")',
  }

  it('discriminates on `program`, because both shapes carry a `status`', () => {
    expect(isServedRender(served)).toBe(true)
    expect(isPendingRender(served)).toBe(false)
    // `status: 'generating'` would pass any `'status' in value` test, which is exactly the
    // bug this guard exists to prevent.
    expect(isServedRender({ status: 'generating', request_id: 'req-1' })).toBe(false)
    expect(isPendingRender({ status: 'pending', request_id: null })).toBe(true)
    expect(isServedRender(undefined)).toBe(false)
    expect(isPendingRender(undefined)).toBe(false)
  })
})

describe('error narrowing', () => {
  it('recognises the 409 that needs a human, and only that one', () => {
    expect(
      isNodeNotReviewed(new ApiError(409, { detail: 'x', field: 'node_not_reviewed' })),
    ).toBe(true)
    expect(isNodeNotReviewed(new ApiError(409, { detail: 'x', field: 'item_id' }))).toBe(false)
    expect(isNodeNotReviewed(new ApiError(404, { detail: 'x' }))).toBe(false)
    expect(isNodeNotReviewed(new Error('boom'))).toBe(false)
  })

  it('reads a 404 as "this surface does not exist" (flag off, or a static course)', () => {
    expect(isNodeSurfaceDisabled(new ApiError(404, { detail: 'Not Found' }))).toBe(true)
    expect(isNodeSurfaceDisabled(new ApiError(500, { detail: 'boom' }))).toBe(false)
  })
})

describe('elementForFormat', () => {
  it('maps a format to one of the four `format_vector` dimensions', () => {
    expect(elementForFormat('chart')).toBe('dato')
    expect(elementForFormat('exercise')).toBe('ejercicio')
    expect(elementForFormat('explanation')).toBe('texto')
    expect(elementForFormat('mixed')).toBe('texto')
    // Reserved and never emitted (§1.3) — but it must not produce a dimension the vector
    // silently drops on the floor.
    expect(elementForFormat('simulation')).toBe('texto')
    expect(elementForFormat(null)).toBe('texto')
  })
})
