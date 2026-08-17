import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { useChat } from './chat'

/**
 * The chat stream parser, on its own.
 *
 * What is being defended here is a *feel*, and feels regress silently. The tutor now
 * answers in two beats — prose, then optionally the same answer laid out in blocks — and
 * the whole design rests on the second beat costing the first one nothing. Two assertions
 * carry that: `isStreaming` goes false at `done` (not when the reader drains), and a
 * layout that never validates leaves a bubble identical to yesterday's.
 */

const mockFetch = vi.fn()

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

const PROGRAM =
  'root = Stack([intro], "md")\nintro = TextContent("Los alergenos son 14.", "lead")\n'

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useChat', () => {
  it('labels the answer with the grounding the server decided', async () => {
    install([
      event('grounding', { grounding: 'document' }),
      event('token', { content: 'Los alergenos ' }),
      event('token', { content: 'son 14.' }),
      event('citations', { citations: [{ document: 'Manual', section: 'documento completo' }] }),
      event('done', { message_id: 'm1' }),
    ])

    const { result } = renderHook(() => useChat('/chat'))
    await act(async () => {
      await result.current.sendMessage('¿Qué son los alérgenos?')
    })

    await waitFor(() => expect(result.current.messages).toHaveLength(2))
    const answer = result.current.messages[1]
    expect(answer.grounding).toBe('document')
    expect(answer.content).toBe('Los alergenos son 14.')
    expect(answer.citations).toHaveLength(1)
    expect(answer.isStreaming).toBe(false)
  })

  it('marks a general-knowledge answer as such', async () => {
    install([
      event('grounding', { grounding: 'general' }),
      event('token', { content: 'En general...' }),
      event('done', { message_id: 'm1' }),
    ])

    const { result } = renderHook(() => useChat('/chat'))
    await act(async () => {
      await result.current.sendMessage('que es un alergeno')
    })

    await waitFor(() => expect(result.current.messages[1].grounding).toBe('general'))
    expect(result.current.messages[1].content).toBe('En general...')
  })

  it('accepts a program that arrives after `done`', async () => {
    install([
      event('grounding', { grounding: 'document' }),
      event('token', { content: 'Los alergenos son 14.' }),
      event('done', { message_id: 'm1' }),
      event('layout_start', {}),
      event('ui', { program: PROGRAM, format: 'explanation' }),
    ])

    const { result } = renderHook(() => useChat('/chat'))
    await act(async () => {
      await result.current.sendMessage('¿alergenos?')
    })

    await waitFor(() => expect(result.current.messages[1].program).toBe(PROGRAM))
    // The prose is never discarded: it is what the bubble falls back to.
    expect(result.current.messages[1].content).toBe('Los alergenos son 14.')
    expect(result.current.messages[1].isLayingOut).toBe(false)
  })

  it('gives the composer back at `done`, not at the end of the stream', async () => {
    // The layout call takes real seconds on a real provider, so the gap between `done`
    // and `ui` is held open here on purpose: that gap is exactly the window in which the
    // old code left the input disabled, and this asserts it no longer does.
    const encoder = new TextEncoder()
    const before = [
      event('token', { content: 'Respuesta.' }),
      event('done', { message_id: 'm1' }),
    ]
    let releaseLayout: () => void = () => {}
    const layoutHeld = new Promise<void>((resolve) => {
      releaseLayout = resolve
    })
    let index = 0
    mockFetch.mockImplementation(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        body: {
          getReader: () => ({
            read: async () => {
              if (index < before.length) {
                return { done: false, value: encoder.encode(before[index++]) }
              }
              if (index === before.length) {
                await layoutHeld
                index += 1
                return {
                  done: false,
                  value: encoder.encode(event('ui', { program: PROGRAM, format: 'explanation' })),
                }
              }
              return { done: true, value: undefined }
            },
          }),
        },
      }),
    )

    const { result } = renderHook(() => useChat('/chat'))
    let pending: Promise<void> | undefined
    await act(async () => {
      pending = result.current.sendMessage('hola')
      await Promise.resolve()
    })

    // Mid-stream: the answer is complete, the connection is not.
    await waitFor(() => expect(result.current.messages[1].isStreaming).toBe(false))
    expect(result.current.isStreaming).toBe(false)
    expect(result.current.messages[1].program).toBeUndefined()

    await act(async () => {
      releaseLayout()
      await pending
    })
    expect(result.current.messages[1].program).toBe(PROGRAM)
  })

  it('leaves yesterday’s bubble when the layout is skipped', async () => {
    install([
      event('token', { content: 'Respuesta en prosa.' }),
      event('done', { message_id: 'm1' }),
      event('layout_start', {}),
      event('layout_skipped', {}),
    ])

    const { result } = renderHook(() => useChat('/chat'))
    await act(async () => {
      await result.current.sendMessage('hola')
    })

    await waitFor(() => expect(result.current.messages[1].isLayingOut).toBe(false))
    expect(result.current.messages[1].program).toBeUndefined()
    expect(result.current.messages[1].content).toBe('Respuesta en prosa.')
  })

  it('survives a stream that stops before any layout event', async () => {
    install([event('token', { content: 'Media ' }), event('token', { content: 'respuesta' })])

    const { result } = renderHook(() => useChat('/chat'))
    await act(async () => {
      await result.current.sendMessage('hola')
    })

    await waitFor(() => expect(result.current.messages[1].isStreaming).toBe(false))
    expect(result.current.messages[1].content).toBe('Media respuesta')
    expect(result.current.isStreaming).toBe(false)
  })

  it('reports a server error in the bubble', async () => {
    install([event('error', { detail: 'Chat services are not configured.' })])

    const { result } = renderHook(() => useChat('/chat'))
    await act(async () => {
      await result.current.sendMessage('hola')
    })

    await waitFor(() =>
      expect(result.current.messages[1].content).toBe('Chat services are not configured.'),
    )
    expect(result.current.messages[1].isStreaming).toBe(false)
  })

  it('threads later turns onto the session the server opened (conversation memory)', async () => {
    // The server reports the session id on `done`; every turn after the first must send it
    // back so the tutor loads the conversation's history and follow-ups resolve in-thread.
    let call = 0
    mockFetch.mockImplementation((_url: string, init: RequestInit) => {
      call += 1
      const body = JSON.parse(String(init.body)) as Record<string, unknown>
      if (call === 1) {
        expect(body.session_id).toBeUndefined() // first turn opens a session
        return sseResponse([
          event('token', { content: 'Primera.' }),
          event('done', { message_id: 'm1', session_id: 'sess-42' }),
        ])
      }
      expect(body.session_id).toBe('sess-42') // second turn threads onto it
      return sseResponse([
        event('token', { content: 'Segunda.' }),
        event('done', { message_id: 'm2', session_id: 'sess-42' }),
      ])
    })

    const { result } = renderHook(() => useChat('/chat'))
    await act(async () => {
      await result.current.sendMessage('primera')
    })
    await act(async () => {
      await result.current.sendMessage('y los pasos?')
    })

    expect(call).toBe(2)
  })
})
