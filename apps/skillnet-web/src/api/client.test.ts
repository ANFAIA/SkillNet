import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { get, post, put, del, upload, loginRequest, ApiError } from './client'

// Mock global fetch
const mockFetch = vi.fn()

beforeEach(() => {
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
})

function jsonResponse(data: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
  })
}

function errorResponse(status: number, body: { detail: string }) {
  return Promise.resolve({
    ok: false,
    status,
    json: () => Promise.resolve(body),
  })
}

describe('API client', () => {
  describe('get()', () => {
    it('calls fetch with correct URL and credentials', async () => {
      mockFetch.mockReturnValue(jsonResponse({ id: 1 }))

      const result = await get('/users/me')

      expect(mockFetch).toHaveBeenCalledWith('/api/v1/users/me', {
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        signal: expect.any(AbortSignal),
      })
      expect(result).toEqual({ id: 1 })
    })
  })

  describe('post()', () => {
    it('sends POST with JSON body', async () => {
      mockFetch.mockReturnValue(jsonResponse({ id: 2 }))

      const result = await post('/courses', { title: 'Test' })

      expect(mockFetch).toHaveBeenCalledWith('/api/v1/courses', {
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        method: 'POST',
        body: JSON.stringify({ title: 'Test' }),
        signal: expect.any(AbortSignal),
      })
      expect(result).toEqual({ id: 2 })
    })

    it('sends POST without body when body is undefined', async () => {
      mockFetch.mockReturnValue(jsonResponse({ ok: true }))

      await post('/trigger')

      expect(mockFetch).toHaveBeenCalledWith('/api/v1/trigger', {
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        method: 'POST',
        body: undefined,
        signal: expect.any(AbortSignal),
      })
    })
  })

  describe('put()', () => {
    it('sends PUT with JSON body', async () => {
      mockFetch.mockReturnValue(jsonResponse({ updated: true }))

      await put('/courses/1', { title: 'Updated' })

      expect(mockFetch).toHaveBeenCalledWith('/api/v1/courses/1', {
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        method: 'PUT',
        body: JSON.stringify({ title: 'Updated' }),
        signal: expect.any(AbortSignal),
      })
    })
  })

  describe('del()', () => {
    it('sends DELETE and handles 204 No Content', async () => {
      mockFetch.mockReturnValue(
        Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve(null) }),
      )

      const result = await del('/courses/1')
      expect(result).toBeUndefined()
    })
  })

  describe('upload()', () => {
    it('sends FormData without Content-Type header', async () => {
      mockFetch.mockReturnValue(jsonResponse({ fileId: 'abc' }))
      const formData = new FormData()

      await upload('/documents/upload', formData)

      expect(mockFetch).toHaveBeenCalledWith('/api/v1/documents/upload', {
        credentials: 'include',
        headers: {},
        method: 'POST',
        body: formData,
        signal: expect.any(AbortSignal),
      })
    })
  })

  describe('error handling', () => {
    it('throws ApiError with status and body on non-ok responses', async () => {
      mockFetch.mockReturnValue(
        errorResponse(422, { detail: 'Validation failed' }),
      )

      await expect(get('/bad')).rejects.toThrow(ApiError)

      try {
        await get('/bad')
      } catch (err) {
        const apiErr = err as ApiError
        expect(apiErr.status).toBe(422)
        expect(apiErr.body.detail).toBe('Validation failed')
        expect(apiErr.message).toBe('Validation failed')
      }
    })

    it('throws ApiError with 401 on unauthorized', async () => {
      mockFetch.mockReturnValue(
        Promise.resolve({ ok: false, status: 401, json: () => Promise.resolve({}) }),
      )

      await expect(get('/protected')).rejects.toThrow(ApiError)

      try {
        await get('/protected')
      } catch (err) {
        expect((err as ApiError).status).toBe(401)
        expect((err as ApiError).body.detail).toBe('Unauthorized')
      }
    })

    it('handles non-JSON error responses gracefully', async () => {
      mockFetch.mockReturnValue(
        Promise.resolve({
          ok: false,
          status: 500,
          json: () => Promise.reject(new Error('not json')),
        }),
      )

      await expect(get('/crash')).rejects.toThrow('Unknown error')
    })

    it('throws when success response is not JSON', async () => {
      mockFetch.mockReturnValue(
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.reject(new Error('not json')),
        }),
      )

      await expect(get('/html-page')).rejects.toThrow(ApiError)
    })
  })

  describe('timeouts', () => {
    it('passes an abort signal so a stalled request cannot hang forever', async () => {
      mockFetch.mockReturnValue(jsonResponse({ ok: true }))

      await get('/anything')

      const init = mockFetch.mock.calls[0][1] as RequestInit
      expect(init.signal).toBeInstanceOf(AbortSignal)
      expect(init.signal?.aborted).toBe(false)
    })

    it('turns a TimeoutError into a 408 ApiError', async () => {
      mockFetch.mockRejectedValue(
        new DOMException('The operation timed out.', 'TimeoutError'),
      )

      try {
        await get('/slow')
        expect.unreachable('should have thrown')
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError)
        expect((err as ApiError).status).toBe(408)
        expect((err as ApiError).body.code).toBe('REQUEST_TIMEOUT')
      }
    })

    it('lets a caller abort propagate as an abort, not a server error', async () => {
      mockFetch.mockRejectedValue(new DOMException('Aborted.', 'AbortError'))

      await expect(get('/cancelled')).rejects.toThrowError(
        expect.objectContaining({ name: 'AbortError' }),
      )
    })
  })

  describe('loginRequest()', () => {
    it('sends URL-encoded form data to /auth/login', async () => {
      mockFetch.mockReturnValue(
        Promise.resolve({ ok: true, status: 200 }),
      )

      await loginRequest('user@example.com', 'secret123')

      expect(mockFetch).toHaveBeenCalledWith('/api/v1/auth/login', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: 'username=user%40example.com&password=secret123',
        signal: expect.any(AbortSignal),
      })
    })

    it('throws ApiError on login failure', async () => {
      mockFetch.mockReturnValue(
        errorResponse(400, { detail: 'LOGIN_BAD_CREDENTIALS' }),
      )

      await expect(
        loginRequest('bad@example.com', 'wrong'),
      ).rejects.toThrow(ApiError)
    })
  })
})
