/**
 * `POST /explain` — the client half of click-to-explain (§8.3, §8.4).
 *
 * Not a TanStack Query hook: an explanation is a streamed side effect of a click, not
 * cached server state, and the backend already owns the cache (`term_explanations`)
 * that makes the second identical click free. It streams over `fetch` +
 * `ReadableStream` rather than `EventSource` for the same reason `api/chat.ts` does:
 * the request needs a POST body and a clean `AbortController` cancel.
 *
 * The `token` event carries the **full cleaned text so far**, not a delta — the
 * server's contract, because stripping a leaked label can rewrite a prefix that was
 * already sent, and because a cache hit is a single `token` with the whole answer.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from './client'

/** Block context is clamped to 600 characters CENTERED on the term (§8.3). */
export const CONTEXT_MAX_CHARS = 600

/** Hard ceiling on a selection: more than this is not a term, it is a paragraph (§8.4). */
export const TERM_MAX_LENGTH = 140

export interface ExplainRequestBody {
  term: string
  context: string
  node_id?: string | null
  language?: string
}

export type ExplainStatus = 'idle' | 'loading' | 'ready' | 'error'

/** Mirror of `explain_service.normalize_context`. */
export function normalizeContext(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}

/** Mirror of `explain_service.normalize_term`. */
export function normalizeTerm(term: string): string {
  return normalizeContext(term).toLowerCase()
}

/**
 * The 600-character window **centered on the term**, not the first 600 characters.
 *
 * This is the §8.3 correction to the original: in a long block the clicked term could
 * fall outside the context sent to the model, which is the worst failure the feature
 * has — the model is asked about a word it cannot see. Idempotent, and identical to
 * the server's `center_context`, so both sides hash the same string.
 */
export function centerContext(
  context: string,
  term: string,
  maxChars: number = CONTEXT_MAX_CHARS,
): string {
  const normalized = normalizeContext(context)
  if (normalized.length <= maxChars) return normalized

  const needle = normalizeTerm(term)
  const position = needle ? normalized.toLowerCase().indexOf(needle) : -1
  if (position < 0) return normalized.slice(0, maxChars).trim()

  const center = position + Math.floor(needle.length / 2)
  let start = Math.max(0, center - Math.floor(maxChars / 2))
  start = Math.min(start, normalized.length - maxChars)
  return normalized.slice(start, start + maxChars).trim()
}

export interface StreamExplainOptions {
  signal?: AbortSignal
  /** Called with the full text so far on every `token` event. */
  onText?: (text: string) => void
  /**
   * Called once with the canonical OpenUI program when the server emits a `ui`
   * event. The program is server-written from the same sentence the `token` events
   * carry, so a client that ignores it still shows the plain text — the program is
   * the richer rendering, the text is the always-present fallback.
   */
  onProgram?: (program: string) => void
}

export interface ExplainOutcome {
  explanation: string
  cached: boolean
  /** Canonical OpenUI program, or `null` when none was emitted (serve the text). */
  program: string | null
}

/**
 * Stream one explanation. Rejects with `ApiError` for a non-2xx status (422 for an
 * over-long selection, 429 for the rate limit, 404 when the feature flag is off) and
 * with a plain `Error` for an in-band `error` event.
 */
export async function streamExplain(
  body: ExplainRequestBody,
  { signal, onText, onProgram }: StreamExplainOptions = {},
): Promise<ExplainOutcome> {
  const res = await fetch('/api/v1/explain', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  })

  if (!res.ok) {
    const parsed = (await res.json().catch(() => ({ detail: 'Error desconocido' }))) as {
      detail?: unknown
    }
    const detail =
      typeof parsed.detail === 'string' ? parsed.detail : 'No se pudo explicar el termino'
    throw new ApiError(res.status, { detail })
  }
  if (!res.body) throw new Error('La respuesta no trae cuerpo')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let eventType = ''
  let text = ''
  let cached = false
  let program: string | null = null
  let failure: string | null = null

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      if (line.startsWith('event:')) {
        eventType = line.slice(6).trim()
        continue
      }
      if (!line.startsWith('data:')) continue
      const raw = line.slice(5).trim()
      if (!raw) continue
      let data: Record<string, unknown>
      try {
        data = JSON.parse(raw) as Record<string, unknown>
      } catch {
        continue
      }

      if (eventType === 'token') {
        text = String(data.content ?? '')
        onText?.(text)
      } else if (eventType === 'ui') {
        program = String(data.program ?? '')
        if (program) onProgram?.(program)
      } else if (eventType === 'done') {
        if (typeof data.explanation === 'string') {
          text = data.explanation
          onText?.(text)
        }
        cached = data.cached === true
      } else if (eventType === 'error') {
        failure = String(data.detail ?? 'No se pudo explicar el termino')
      }
      eventType = ''
    }
  }

  if (failure) throw new Error(failure)
  return { explanation: text, cached, program }
}

export interface UseExplainResult {
  status: ExplainStatus
  text: string
  /**
   * Canonical OpenUI program for the glimpse, or `null` when none arrived. When set,
   * the popover renders it through the shared `UiSpecRenderer`; when `null` (or the
   * program fails the client gate) it shows `text` instead.
   */
  program: string | null
  /** Ready-to-show message. `null` unless `status === 'error'`. */
  error: string | null
  run: (body: ExplainRequestBody) => void
  reset: () => void
}

const RATE_LIMIT_MESSAGE = 'Demasiadas consultas seguidas'

/**
 * Drive one explanation request at a time. A new `run` aborts the previous one, so
 * clicking through five words in a row leaves four cancelled requests and one answer
 * instead of five answers racing to land in the same popover.
 */
export function useExplain(): UseExplainResult {
  const [status, setStatus] = useState<ExplainStatus>('idle')
  const [text, setText] = useState('')
  const [program, setProgram] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Abort whatever is in flight when the popover unmounts, so closing it stops
  // paying for the answer nobody will read.
  useEffect(() => () => abortRef.current?.abort(), [])

  const run = useCallback((body: ExplainRequestBody) => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setStatus('loading')
    setText('')
    setProgram(null)
    setError(null)

    streamExplain(body, {
      signal: controller.signal,
      onText: (value) => {
        if (!controller.signal.aborted) setText(value)
      },
      onProgram: (value) => {
        if (!controller.signal.aborted) setProgram(value)
      },
    })
      .then(() => {
        if (controller.signal.aborted) return
        setStatus('ready')
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return
        if (err instanceof DOMException && err.name === 'AbortError') return
        const message =
          err instanceof ApiError && err.status === 429
            ? RATE_LIMIT_MESSAGE
            : err instanceof Error
              ? err.message
              : 'No se pudo explicar el termino'
        setError(message)
        setStatus('error')
      })
  }, [])

  const reset = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setStatus('idle')
    setText('')
    setProgram(null)
    setError(null)
  }, [])

  return { status, text, program, error, run, reset }
}
