/**
 * Runtime employee API for dynamic courses (§11.3) — the client half of B5.
 *
 * Three things here are load bearing and not stylistic:
 *
 * 1. **`useNodeRender` never refetches on window focus.** The server already pins
 *    `active_render_id` and recomputes nothing on `GET /render` (§5.5), so a refetch
 *    returns the same bytes; the flag is belt over braces, and it also documents that
 *    the "Estable" row of the spatial-stability table is not maintained by luck.
 * 2. **`POST /render` may answer without a stream.** `request_id === ''` with
 *    `cached: true` means the render was already pinned or hit the cache: subscribing
 *    then would hang on a channel nobody will ever publish to. Only a non-empty
 *    `request_id` has work to listen to, and the subscription must happen immediately
 *    (the runner waits 0.5 s for a subscriber and this pub/sub keeps no backlog).
 * 3. **`ui_block` events are progress, never content.** They come from
 *    `backend.parse_partial` *before* `validate_ui` runs, so the components in them have
 *    not been through the gate. The only text the browser parses is `program` from
 *    `GET /render`, which is re-serialized from the validated `UISpec` (§5.1). This hook
 *    counts the blocks and forgets them.
 *
 * `hints_used` in a `POST /answer` body is informative and the server ignores it (§11.3):
 * the count of record is `node_attempts.hints_used`, which only `POST /nodes/{id}/hint`
 * moves. Everything here sends `0`.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, get, post } from './client'
import type {
  NodeAttemptOutcome,
  NodeEventInput,
  NodeFeedbackBody,
  NodeList,
  NodeRender,
  NodeRenderAccepted,
  NodeRenderHistory,
  NodeRenderPending,
} from '../types'
import type { UiFormat } from '../types/node-render'

// --------------------------------------------------------------------------- //
// Query keys
// --------------------------------------------------------------------------- //

/** The node list of a course. Invalidated by every answer (mastery moved). */
export const courseNodesKey = (courseId: string | undefined) =>
  ['nodes', 'course', courseId] as const

/**
 * The pinned render of one node for the current learner.
 *
 * `previewPref` (admin demo preview only) is part of the key so the audio and visual
 * variants are cached as separate entries and toggling between them does not clobber
 * one with the other.
 */
export const nodeRenderKey = (
  nodeId: string | undefined,
  previewPref?: 'audio' | 'visual',
) => ['nodes', nodeId, 'render', previewPref ?? 'default'] as const

/** "Ver la version anterior" (§5.5) — the renders *this* learner was served. */
export const nodeRenderHistoryKey = (nodeId: string | undefined) =>
  ['nodes', nodeId, 'renders'] as const

/** One superseded version, by id. Immutable once written, so it is cached forever. */
export const nodeRenderVersionKey = (
  nodeId: string | undefined,
  renderId: string | undefined,
) => ['nodes', nodeId, 'renders', renderId] as const

// --------------------------------------------------------------------------- //
// Error narrowing
// --------------------------------------------------------------------------- //

/**
 * `409 node_not_reviewed` (§3.2): the course is validated but no human signed this
 * node off, so it can never be served.
 *
 * Not a transient failure and **not** something to retry: an admin has to review the
 * node. Retrying would loop against a blank screen forever.
 */
export function isNodeNotReviewed(error: unknown): boolean {
  return (
    error instanceof ApiError && error.status === 409 && error.body.field === 'node_not_reviewed'
  )
}

/**
 * With the flag anywhere but `on`, the whole employee runtime surface 404s —
 * indistinguishable from routes that do not exist (§10.1). A static course's node list
 * 404s for the same reason, which is what makes the discriminator in `CourseView` work.
 */
export function isNodeSurfaceDisabled(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404
}

// --------------------------------------------------------------------------- //
// Node list
// --------------------------------------------------------------------------- //

/**
 * `GET /courses/{course_id}/nodes` — the node list with per-learner state (§11.3).
 *
 * `enabled` is how `CourseView` avoids a request it knows will 404: with the flag off
 * there is no employee surface at all. `retry: false` because the two interesting
 * failures (404 flag/static, 409 unreviewed) are answers, not glitches.
 */
export function useCourseNodes(
  courseId: string | undefined,
  options: { enabled?: boolean } = {},
) {
  const { enabled = true } = options
  return useQuery({
    queryKey: courseNodesKey(courseId),
    queryFn: () => get<NodeList>(`/courses/${courseId}/nodes`),
    enabled: !!courseId && enabled,
    retry: false,
  })
}

// --------------------------------------------------------------------------- //
// Render
// --------------------------------------------------------------------------- //

/** `202` bodies of `GET /render` are data, not errors. */
export type NodeRenderResponse = NodeRender | NodeRenderPending

/**
 * True when the response carries a program the browser may render.
 *
 * Discriminated on `program`, not on `status`: **both** shapes have a `status` field
 * (`NodeRender.status` is `ready`/`fallback`/…, `NodeRenderPending.status` is
 * `pending`/`generating`), so `'status' in value` narrows nothing.
 */
export function isServedRender(value: NodeRenderResponse | undefined): value is NodeRender {
  return !!value && 'program' in value && typeof value.program === 'string'
}

/** The `202` half of the same union: nothing pinned yet. */
export function isPendingRender(
  value: NodeRenderResponse | undefined,
): value is NodeRenderPending {
  return !!value && !isServedRender(value)
}

/**
 * `GET /nodes/{node_id}/render` — the **pinned** render (§5.5).
 *
 * `refetchOnWindowFocus: false` per §13 B9. The server would return identical bytes,
 * but a screen that re-renders the lesson every time the learner alt-tabs is exactly
 * the instability the pinning exists to prevent, and one day somebody will change the
 * server. `staleTime: Infinity` for the same reason: within an open node the only thing
 * that may replace the content is the "Actualizar esta leccion" button.
 */
export function useNodeRender(
  nodeId: string | undefined,
  options: {
    enabled?: boolean
    refetchInterval?: number | false
    /**
     * Admin demo preview only: fetch a pre-baked personalization variant of the same
     * lesson (`audio` or `visual`) via `?preview_pref=`. Absent = normal per-learner
     * pinned render. Each value is cached separately (see `nodeRenderKey`).
     */
    previewPref?: 'audio' | 'visual'
  } = {},
) {
  const { enabled = true, refetchInterval = false, previewPref } = options
  return useQuery({
    queryKey: nodeRenderKey(nodeId, previewPref),
    queryFn: () =>
      get<NodeRenderResponse>(
        previewPref
          ? `/nodes/${nodeId}/render?preview_pref=${previewPref}`
          : `/nodes/${nodeId}/render`,
      ),
    enabled: !!nodeId && enabled,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    // Off by default (a pinned lesson never changes under the learner). Turned on only
    // while a node is "Preparándose…", so the screen flips to the real episode by itself
    // the moment its knowledge pack lands and the fallback pin is dropped server-side.
    refetchInterval,
  })
}

/**
 * `POST /nodes/{node_id}/render` — ask for a render (§11.3).
 *
 * Used for all three reasons a render starts: the prefetch of the productive wait
 * (§9.1), the first request when the probe ends in `learning`, and
 * `force: true` from "Actualizar esta leccion" (§5.5, the only way an open node's
 * content changes).
 *
 * Not in the §13 B9 hook list, which names `useNodeRender` for reading only — but the
 * POST is the other half of every one of those flows and it cannot live in a component
 * without duplicating the `202`/`cached` handling three times.
 */
export function useRequestRender(nodeId: string | undefined) {
  return useMutation({
    mutationFn: (input: { force?: boolean; preview?: boolean } = {}) =>
      post<NodeRenderAccepted>(`/nodes/${nodeId}/render`, {
        force: input.force ?? false,
        preview: input.preview ?? false,
      }),
  })
}

/** `GET /nodes/{node_id}/renders` — the version list behind "Ver la version anterior". */
export function useNodeRenderHistory(
  nodeId: string | undefined,
  options: { enabled?: boolean } = {},
) {
  const { enabled = true } = options
  return useQuery({
    queryKey: nodeRenderHistoryKey(nodeId),
    queryFn: () => get<NodeRenderHistory>(`/nodes/${nodeId}/renders`),
    enabled: !!nodeId && enabled,
    retry: false,
  })
}

/**
 * `GET /nodes/{node_id}/renders/{render_id}` — **one** version out of that list.
 *
 * The endpoint the version list spent a batch without. Before it existed a version was
 * only reopenable while this session still held its program in memory, so a reload emptied
 * the feature and a version from last week was a dead entry with a date on it. The server
 * authorizes by `node_render_views` (the record that *this* learner was served *that*
 * render), pins nothing and records no new view: looking back at something already seen is
 * not being served it, and moving `first_seen_at` would corrupt the evidence a certificate
 * rests on.
 *
 * `staleTime: Infinity` because an old version is immutable by construction — `node_renders`
 * rows are never rewritten, only superseded.
 */
export function useNodeRenderVersion(
  nodeId: string | undefined,
  renderId: string | null | undefined,
) {
  return useQuery({
    queryKey: nodeRenderVersionKey(nodeId, renderId ?? undefined),
    queryFn: () => get<NodeRender>(`/nodes/${nodeId}/renders/${renderId}`),
    enabled: !!nodeId && !!renderId,
    retry: false,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  })
}

// --------------------------------------------------------------------------- //
// Render stream (SSE, §9.2)
// --------------------------------------------------------------------------- //

export type RenderStreamStatus = 'idle' | 'streaming' | 'done' | 'skipped' | 'error'

export interface RenderStreamState {
  status: RenderStreamStatus
  /** Graph node currently running (`decide_formato`, `genera_ui`, …). */
  step: string | null
  /** The server's own sentence for that step, ready to print. */
  message: string | null
  /** From `ui_format`: lets the skeleton take the shape the lesson will have. */
  format: UiFormat | null
  /** How many components `parse_partial` has completed. Progress only — never content. */
  blocks: number
  /** `node_renders.id`, from `ui_done`. */
  renderId: string | null
  /** `node_skipped`: the gate found the node already mastered. */
  skipped: boolean
  error: string | null
  /**
   * `error.fallback`. `true` → ask `GET /render` again and the seed lesson is there;
   * `false` → there is nothing to serve and asking again is a loop against a blank
   * screen.
   */
  fallbackAvailable: boolean
}

const IDLE_STREAM: RenderStreamState = {
  status: 'idle',
  step: null,
  message: null,
  format: null,
  blocks: 0,
  renderId: null,
  skipped: false,
  error: null,
  fallbackAvailable: false,
}

/** The events after which the server closes the stream. */
const TERMINAL_EVENTS = new Set(['ui_done', 'node_skipped', 'error'])

const UI_FORMATS: readonly UiFormat[] = [
  'explanation',
  'simulation',
  'exercise',
  'chart',
  'mixed',
]

function asUiFormat(value: unknown): UiFormat | null {
  return typeof value === 'string' && (UI_FORMATS as readonly string[]).includes(value)
    ? (value as UiFormat)
    : null
}

export interface RenderStreamHandlers {
  /** Fired once, on the first terminal event. `reason` says which one. */
  onSettled?: (outcome: {
    reason: 'done' | 'skipped' | 'error'
    renderId: string | null
    fallbackAvailable: boolean
  }) => void
}

/**
 * Consume `GET /nodes/{node_id}/render/stream?request_id=…`.
 *
 * `fetch` + `ReadableStream` rather than `EventSource`, like `api/explain.ts` and
 * `api/chat.ts`: `EventSource` cannot be aborted cleanly, cannot be told to stop
 * reconnecting, and this stream must die the moment the learner leaves the node.
 *
 * **Truncation is normal, not exceptional.** The connection can end at any byte: mid
 * `data:` line, between `event:` and its payload, or after ten `ui_block`s and no
 * `ui_done`. Every one of those leaves the state machine in `streaming` and lets the
 * caller fall back to `GET /render`; none of them throws. That is why the parser keeps
 * a buffer and only acts on complete lines, and why a `JSON.parse` failure skips the
 * line instead of failing the stream.
 */
export function useNodeRenderStream(handlers: RenderStreamHandlers = {}) {
  const [state, setState] = useState<RenderStreamState>(IDLE_STREAM)
  const abortRef = useRef<AbortController | null>(null)
  const settledRef = useRef(false)
  const handlersRef = useRef(handlers)
  handlersRef.current = handlers

  const stop = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
  }, [])

  // Leaving the node stops paying for a stream nobody will read.
  useEffect(() => () => abortRef.current?.abort(), [])

  const start = useCallback(
    async (nodeId: string, requestId: string) => {
      if (!nodeId || !requestId) return
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      settledRef.current = false
      setState({ ...IDLE_STREAM, status: 'streaming' })

      const settle = (
        reason: 'done' | 'skipped' | 'error',
        renderId: string | null,
        fallbackAvailable: boolean,
      ) => {
        if (settledRef.current) return
        settledRef.current = true
        handlersRef.current.onSettled?.({ reason, renderId, fallbackAvailable })
      }

      try {
        const res = await fetch(
          `/api/v1/nodes/${nodeId}/render/stream?request_id=${encodeURIComponent(requestId)}`,
          {
            credentials: 'include',
            headers: { Accept: 'text/event-stream' },
            signal: controller.signal,
          },
        )
        if (!res.ok || !res.body) {
          // No stream to read. The render may still be running server-side, so this is
          // not a content failure: the caller polls `GET /render`.
          setState((prev) => ({ ...prev, status: 'streaming' }))
          return
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let eventType = ''

        for (;;) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          // The last element is whatever came after the final newline: an incomplete
          // line, kept for the next chunk. A stream cut here simply never completes it.
          buffer = lines.pop() ?? ''

          let terminal: { reason: 'done' | 'skipped' | 'error' } | null = null

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
              // A half-arrived payload. Drop the line, keep the stream.
              eventType = ''
              continue
            }

            const type = eventType
            eventType = ''

            if (type === 'render_step') {
              setState((prev) => ({
                ...prev,
                step: typeof data.step === 'string' ? data.step : prev.step,
                message: typeof data.message === 'string' ? data.message : prev.message,
              }))
            } else if (type === 'ui_format') {
              const format = asUiFormat(data.format)
              setState((prev) => ({ ...prev, format: format ?? prev.format }))
            } else if (type === 'ui_block') {
              // Counted, never rendered: these components have not been through the
              // validation gate. See rule 5 in the module docstring.
              setState((prev) => ({ ...prev, blocks: prev.blocks + 1 }))
            } else if (type === 'ui_done') {
              const renderId = typeof data.render_id === 'string' ? data.render_id : null
              setState((prev) => ({ ...prev, status: 'done', renderId }))
              settle('done', renderId, false)
              terminal = { reason: 'done' }
            } else if (type === 'node_skipped') {
              setState((prev) => ({ ...prev, status: 'skipped', skipped: true }))
              settle('skipped', null, false)
              terminal = { reason: 'skipped' }
            } else if (type === 'error') {
              const fallback = data.fallback === true
              const message =
                typeof data.message === 'string' && data.message.trim()
                  ? data.message
                  : 'No se pudo preparar esta lección.'
              setState((prev) => ({
                ...prev,
                status: 'error',
                error: message,
                fallbackAvailable: fallback,
              }))
              settle('error', null, fallback)
              terminal = { reason: 'error' }
            }

            if (type && TERMINAL_EVENTS.has(type)) break
          }

          if (terminal) break
        }
      } catch (err: unknown) {
        if (controller.signal.aborted) return
        if (err instanceof DOMException && err.name === 'AbortError') return
        // A dropped connection is not a failed render: the graph runs server-side and
        // `GET /render` is the source of truth. Stay in `streaming` so the caller polls.
        setState((prev) => (prev.status === 'streaming' ? prev : { ...prev, status: 'streaming' }))
      } finally {
        if (abortRef.current === controller) abortRef.current = null
      }
    },
    [],
  )

  const reset = useCallback(() => {
    stop()
    settledRef.current = false
    setState(IDLE_STREAM)
  }, [stop])

  return useMemo(() => ({ ...state, start, stop, reset }), [state, start, stop, reset])
}

// --------------------------------------------------------------------------- //
// Answer, hint, feedback, events
// --------------------------------------------------------------------------- //

/**
 * `POST /nodes/{node_id}/answer`.
 *
 * The sanctioned hook for grading an item of a served render. `QuizItemBlock` (B6) has
 * its own inline copy of this mutation because it is instantiated by OpenUI's runtime
 * and predates this file; the two must stay in agreement about `hints_used: 0` and
 * about invalidating `['nodes']`, which is why both carry the same comment.
 */
export function useSubmitNodeAnswer(nodeId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      render_id: string
      item_id: string
      answer: unknown
      latency_ms?: number
    }) =>
      post<NodeAttemptOutcome>(`/nodes/${nodeId}/answer`, {
        ...body,
        // Informative only; the server derives the real count (§11.3).
        hints_used: 0,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
      queryClient.invalidateQueries({ queryKey: ['enrollments'] })
    },
  })
}

// `POST /nodes/{node_id}/hint` has no hook here, and now for the opposite reason to the
// one that used to be written in this spot. It has a caller: `HintLadder`, in
// `components/courses/blocks/QuizItemHints.tsx`. It lives there rather than here for the
// same reason `QuizItemBlock`'s answer mutation does — those components are instantiated
// by OpenUI's runtime, which passes props and nothing else, so a hook lifted to this file
// would have no component able to call it with the item it belongs to.
//
// What changed by wiring it up is worth stating once: `node_attempts.hints_used` only
// moves through that endpoint, and rule 8 of §7.3 needs it at 3. Until something spent a
// hint, `needs_review` was unreachable, `NodeSummaryRead.needs_practice` was permanently
// `false` and the "Para practicar" queue could not fill. It can now.

/** `POST /nodes/{node_id}/feedback` — `204`, and it fires the difficulty signals (§3.3). */
export function useNodeFeedback(nodeId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: NodeFeedbackBody) => post<void>(`/nodes/${nodeId}/feedback`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] })
    },
  })
}

/** Max events in one `POST /events` body — `NodeEventsRequest.events` is capped at 100. */
export const EVENT_BATCH_LIMIT = 100

/** How long a queued event waits for company before being sent. */
export const EVENT_FLUSH_MS = 4000

/**
 * Batched instrumentation (§3.3).
 *
 * Batched because a single event is worth ~0.05 of one dimension of a vector that is
 * read once per node open, so one request per event would be all cost and no
 * information. It is safe to batch generously: `POST /events` deliberately does **not**
 * recompute `format_vector` (B5 documented the decision — the refresh happens when a
 * node closes), so no batch pays for a 30-day scan.
 *
 * `element` must be one of the four `format_vector` dimensions (`texto`, `ejercicio`,
 * `codigo`, `dato`); anything else is stored and then ignored by the vector, which is
 * silent dead weight. `elementForFormat` is the only mapping used.
 */
export function useNodeEvents(nodeId: string | undefined) {
  const queue = useRef<NodeEventInput[]>([])
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const nodeIdRef = useRef(nodeId)
  nodeIdRef.current = nodeId

  const send = useCallback((events: NodeEventInput[]) => {
    const target = nodeIdRef.current
    if (!target || events.length === 0) return
    // Fire and forget: instrumentation must never surface an error to the learner, and
    // losing a batch costs 0.05 of a weight nobody reads until the node closes.
    void post<void>(`/nodes/${target}/events`, { events }).catch(() => undefined)
  }, [])

  const flush = useCallback(() => {
    if (timer.current) {
      clearTimeout(timer.current)
      timer.current = null
    }
    const pending = queue.current
    queue.current = []
    send(pending)
  }, [send])

  const record = useCallback(
    (event: NodeEventInput) => {
      queue.current.push(event)
      if (queue.current.length >= EVENT_BATCH_LIMIT) {
        flush()
        return
      }
      if (!timer.current) {
        timer.current = setTimeout(() => {
          timer.current = null
          flush()
        }, EVENT_FLUSH_MS)
      }
    },
    [flush],
  )

  // Leaving the node flushes what is queued; the batch would otherwise die with the
  // component and the node that produced the most signal would report the least.
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
      timer.current = null
      const pending = queue.current
      queue.current = []
      send(pending)
    },
    [send],
  )

  // Memoized on purpose: callers put this object in effect dependency lists (the dwell
  // event of `NodeView` is emitted from a cleanup), and a fresh object per render would
  // re-run those cleanups on every render and emit a dwell event each time.
  return useMemo(() => ({ record, flush }), [record, flush])
}

/**
 * `ui_format` → `format_vector` dimension (§3.3).
 *
 * The dimensions are the component families the frozen kit can produce, so the mapping
 * is by what the lesson is mostly made of: `chart` is `Chart`/`Table` (`dato`),
 * `exercise` is `QuizItem` (`ejercicio`), and everything textual is `texto`.
 * `simulation` is reserved and never emitted (§1.3); it maps to `texto` so an
 * unexpected value cannot produce an element the vector drops on the floor.
 */
export function elementForFormat(format: UiFormat | null | undefined): string {
  switch (format) {
    case 'chart':
      return 'dato'
    case 'exercise':
      return 'ejercicio'
    default:
      return 'texto'
  }
}
