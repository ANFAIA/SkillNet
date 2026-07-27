import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createElement, type ReactNode } from 'react'
import { NO_ACCESSIBILITY } from './onboarding'
import { useUpdateProfile } from './users'

/**
 * `useUpdateProfile` and the four reading settings of question 5.
 *
 * Why this file exists: `ProfileUpdate.accessibility` used to be a typed field the
 * server dropped on the floor (`UserSelfUpdate` had no such field and pydantic's
 * default is `extra='ignore'`, so `PUT /users/me` answered `200` and changed
 * nothing). `short_blocks` feeds `effective_density` and therefore the render
 * `cache_key` (§3.1), so a setting that looks saved and is not means the learner
 * keeps getting the long-block bucket. These tests pin what goes on the wire; the
 * server half is pinned by `tests/test_user_self_update.py`.
 */

const mockFetch = vi.fn()

function jsonResponse(data: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
  })
}

function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children)
}

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const rendered = renderHook(() => useUpdateProfile(), { wrapper: wrapper(client) })
  return { client, result: rendered.result }
}

function body() {
  const call = mockFetch.mock.calls[0]
  return JSON.parse(call[1].body as string)
}

const USER = {
  id: 'u1',
  email: 'ada@test.dev',
  full_name: 'Ada',
  role: 'employee',
  learning_profile: 'standard',
  accessibility: { ...NO_ACCESSIBILITY, short_blocks: true },
}

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useUpdateProfile', () => {
  it('PUTs the four reading settings to /users/me', async () => {
    mockFetch.mockReturnValue(jsonResponse(USER))
    const { result } = setup()

    result.current.mutate({ accessibility: { ...NO_ACCESSIBILITY, short_blocks: true } })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/users/me',
      expect.objectContaining({ method: 'PUT' }),
    )
    expect(body()).toEqual({
      accessibility: { ...NO_ACCESSIBILITY, short_blocks: true },
    })
  })

  it('sends the whole object so an unchecked box turns the setting back off', async () => {
    mockFetch.mockReturnValue(jsonResponse({ ...USER, accessibility: NO_ACCESSIBILITY }))
    const { result } = setup()

    result.current.mutate({ accessibility: NO_ACCESSIBILITY })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    // Every key travels, explicitly false — the server replaces, it does not merge,
    // so an omitted key would be indistinguishable from "leave it as it was".
    expect(body().accessibility).toEqual({
      short_blocks: false,
      reduce_motion: false,
      high_contrast: false,
      extra_time: false,
    })
  })

  it('does not send accessibility when the caller only changes the name', async () => {
    mockFetch.mockReturnValue(jsonResponse(USER))
    const { result } = setup()

    result.current.mutate({ full_name: 'Grace' })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    // Absent must mean "don't touch", not "clear everything".
    expect(body()).toEqual({ full_name: 'Grace' })
    expect('accessibility' in body()).toBe(false)
  })

  it('seeds the me cache with the user the server returned', async () => {
    mockFetch.mockReturnValue(jsonResponse(USER))
    const { client, result } = setup()

    result.current.mutate({ accessibility: { ...NO_ACCESSIBILITY, short_blocks: true } })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    // The response, not the request: the server is the authority on what got stored.
    expect(client.getQueryData(['users', 'me'])).toEqual(USER)
  })
})
