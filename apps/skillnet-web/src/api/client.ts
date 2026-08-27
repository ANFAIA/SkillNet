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

/**
 * How long a request may hang before it is aborted.
 *
 * Every call here used to be a bare `fetch` with no signal at all, and `fetch` has no
 * timeout of its own: a request whose connection stalls — a redeployed API, a dropped
 * network, a proxy that swallowed the response — never settles, so the promise never
 * rejects and whatever is awaiting it waits forever. That is the mechanism behind a
 * literally infinite spinner, and no amount of error handling downstream can see it.
 *
 * Two minutes is above every legitimately slow call this wrapper makes (the slowest is
 * an LLM write that runs inside its request, `POST /documents/from-idea`, which gets a
 * longer ceiling of its own) and far below "forever". The SSE and streaming paths do
 * **not** go through here — `schemaStream.ts`, `generation.ts`, `chat.ts`, `explain.ts`
 * and `nodes.ts` open their own `fetch` with their own `AbortController` — so a long-
 * lived stream cannot be cut by this.
 */
export const DEFAULT_TIMEOUT_MS = 120_000

/** For the handful of calls that run a model inside the request. */
export const SLOW_TIMEOUT_MS = 300_000

export interface ApiOptions extends RequestInit {
  /** Override {@link DEFAULT_TIMEOUT_MS} for one call. */
  timeoutMs?: number
}

/** The caller's own signal, still bounded by the timeout. */
function requestSignal(signal: AbortSignal | null | undefined, timeoutMs: number): AbortSignal {
  const timeout = AbortSignal.timeout(timeoutMs)
  return signal ? AbortSignal.any([signal, timeout]) : timeout
}

async function api<T>(path: string, options?: ApiOptions): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...init } = options ?? {}
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...init.headers },
      ...init,
      signal: requestSignal(init.signal, timeoutMs),
    })
  } catch (cause) {
    // `AbortSignal.timeout` rejects with a `TimeoutError`; an aborted caller signal
    // rejects with `AbortError` and must stay an abort, not become a server error.
    if (cause instanceof DOMException && cause.name === 'TimeoutError') {
      throw new ApiError(408, {
        detail: 'The server did not answer in time. Check your connection and try again.',
        code: 'REQUEST_TIMEOUT',
      })
    }
    throw cause
  }

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

export const get = <T>(path: string, options?: ApiOptions) => api<T>(path, options)

export const post = <T>(path: string, body?: unknown, options?: ApiOptions) =>
  api<T>(path, {
    ...options,
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  })

export const put = <T>(path: string, body: unknown, options?: ApiOptions) =>
  api<T>(path, { ...options, method: 'PUT', body: JSON.stringify(body) })

export const patch = <T>(path: string, body: unknown, options?: ApiOptions) =>
  api<T>(path, { ...options, method: 'PATCH', body: JSON.stringify(body) })

export const del = <T>(path: string, body?: unknown, options?: ApiOptions) =>
  api<T>(path, {
    ...options,
    method: 'DELETE',
    body: body === undefined ? undefined : JSON.stringify(body),
  })

// Multipart upload — omit Content-Type so the browser sets the boundary. An upload of a
// large PDF is slow for an honest reason, so it gets the generous ceiling.
export const upload = <T>(path: string, formData: FormData, options?: ApiOptions) =>
  api<T>(path, {
    timeoutMs: SLOW_TIMEOUT_MS,
    ...options,
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
    signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS),
  })

  if (!res.ok) {
    const body = (await res.json().catch(() => ({ detail: 'Login failed' }))) as ApiErrorBody
    throw new ApiError(res.status, body)
  }
}
