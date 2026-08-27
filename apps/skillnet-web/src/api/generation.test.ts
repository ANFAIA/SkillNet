import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useGenerationProgress } from './generation'

/**
 * The v1 generation stream, and the one thing it used to get wrong.
 *
 * `connectionFailed` is the switch that starts the REST polling fallback in
 * `CreateCourse.tsx`. It was only ever set inside `catch`, so a stream that ended
 * *cleanly* without a terminal event — nginx closing an idle proxied stream at 300s, a
 * redeployed API, a dropped connection — returned normally with the flag still false.
 * The fallback never engaged and the screen froze on the last step it had seen, even
 * though the server had finished. These tests pin both halves: a clean end with no
 * verdict means failed-over, and a real terminal event does not.
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

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useGenerationProgress', () => {
  it('falls back to polling when the stream ends without a verdict', async () => {
    mockFetch.mockImplementation(() => sseResponse([event('step', { step: 'generating' })]))

    const { result } = renderHook(() => useGenerationProgress('job-1'))

    await waitFor(() => expect(result.current.connectionFailed).toBe(true))
    // The last step it did see is still what the screen shows; polling now carries on.
    expect(result.current.progress.step).toBe('generating')
  })

  it('does not fall back when the job completed', async () => {
    mockFetch.mockImplementation(() =>
      sseResponse([
        event('step', { step: 'generating' }),
        event('completed', { course_id: 'course-9' }),
      ]),
    )

    const { result } = renderHook(() => useGenerationProgress('job-2'))

    await waitFor(() => expect(result.current.progress.step).toBe('published'))
    expect(result.current.progress.courseId).toBe('course-9')
    expect(result.current.connectionFailed).toBe(false)
  })

  it('does not fall back when the job failed', async () => {
    mockFetch.mockImplementation(() =>
      sseResponse([event('error', { message: 'The provider is out of quota.' })]),
    )

    const { result } = renderHook(() => useGenerationProgress('job-3'))

    await waitFor(() => expect(result.current.progress.step).toBe('failed'))
    expect(result.current.progress.error).toBe('The provider is out of quota.')
    expect(result.current.connectionFailed).toBe(false)
  })

  it('ignores keepalive comment frames', async () => {
    mockFetch.mockImplementation(() =>
      sseResponse([
        ': keepalive\n\n',
        event('step', { step: 'reviewing' }),
        event('completed', { course_id: 'course-4' }),
      ]),
    )

    const { result } = renderHook(() => useGenerationProgress('job-4'))

    await waitFor(() => expect(result.current.progress.step).toBe('published'))
    expect(result.current.connectionFailed).toBe(false)
  })

  it('treats a failed connection as a fallback, not a crash', async () => {
    mockFetch.mockImplementation(() => Promise.resolve({ ok: false, status: 502, body: null }))

    const { result } = renderHook(() => useGenerationProgress('job-5'))

    await waitFor(() => expect(result.current.connectionFailed).toBe(true))
  })
})
