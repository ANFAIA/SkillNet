// Base fetch wrapper. No token management — the browser sends the httpOnly
// session cookie on every request via `credentials: 'include'`.

export interface ApiErrorBody {
  detail: string
  code?: string
  field?: string
}

export class ApiError extends Error {
  status: number
  body: ApiErrorBody

  constructor(status: number, body: ApiErrorBody) {
    super(body.detail)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

const BASE = '/api/v1'

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })

  if (res.status === 401) {
    // Session expired or not authenticated. The global QueryCache handler
    // performs the redirect; here we only surface the error.
    throw new ApiError(401, { detail: 'Unauthorized' })
  }

  if (!res.ok) {
    const body = (await res.json().catch(() => ({ detail: 'Unknown error' }))) as ApiErrorBody
    throw new ApiError(res.status, body)
  }

  // 204 No Content (e.g. DELETE responses)
  if (res.status === 204) return undefined as T

  // Guard against non-JSON success responses (e.g. nginx serving HTML for an
  // SPA route that should have been proxied to the API).
  try {
    return (await res.json()) as T
  } catch {
    throw new ApiError(res.status, {
      detail: 'La respuesta del servidor no es valida (no es JSON)',
    })
  }
}

export const get = <T>(path: string) => api<T>(path)

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const put = <T>(path: string, body: unknown) =>
  api<T>(path, { method: 'PUT', body: JSON.stringify(body) })

export const del = <T>(path: string) => api<T>(path, { method: 'DELETE' })

// Multipart upload — omit Content-Type so the browser sets the boundary.
export const upload = <T>(path: string, formData: FormData) =>
  api<T>(path, {
    method: 'POST',
    headers: {},
    body: formData,
  })

// fastapi-users login expects an OAuth2 form: `username` + `password`
// as application/x-www-form-urlencoded. On success the cookie is set.
export async function loginRequest(email: string, password: string): Promise<void> {
  const params = new URLSearchParams()
  params.set('username', email)
  params.set('password', password)

  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: params.toString(),
  })

  if (!res.ok) {
    const body = (await res.json().catch(() => ({ detail: 'Login failed' }))) as ApiErrorBody
    throw new ApiError(res.status, body)
  }
}
