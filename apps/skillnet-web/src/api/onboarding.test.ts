import { createElement, type ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useUpdateLearnerProfile } from './onboarding'

const mockFetch = vi.fn()

function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children)
}

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => vi.restoreAllMocks())

describe('useUpdateLearnerProfile', () => {
  it('PATCHes declared preferences and removes only cached node renders', async () => {
    const response = {
      role_title: null,
      sector: null,
      goal: null,
      experience_level: 'unknown',
      preset: 'standard',
      learning_preferences: {
        version: 2,
        modality: 'visual',
        interaction: 'standard',
        detail: 'detailed',
        images: 'prefer',
      },
      nodes_completed: 0,
      onboarding_completed_at: '2026-08-11T12:00:00Z',
      onboarding_skipped: false,
      calibrating: true,
    } as const
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => response,
    })
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
    client.setQueryData(['nodes', 'n1', 'render'], { stale: true })
    client.setQueryData(['nodes', 'course', 'c1'], { nodes: [] })
    client.setQueryData(['courses'], [])
    const { result } = renderHook(() => useUpdateLearnerProfile(), {
      wrapper: wrapper(client),
    })

    result.current.mutate({ learning_preferences: response.learning_preferences })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/users/me/learner-profile',
      expect.objectContaining({ method: 'PATCH' }),
    )
    expect(JSON.parse(mockFetch.mock.calls[0][1].body)).toEqual({
      learning_preferences: response.learning_preferences,
    })
    expect(client.getQueryData(['nodes', 'n1', 'render'])).toBeUndefined()
    expect(client.getQueryData(['nodes', 'course', 'c1'])).toEqual({ nodes: [] })
    expect(client.getQueryData(['courses'])).toEqual([])
  })
})
