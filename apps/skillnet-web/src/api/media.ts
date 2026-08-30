/**
 * Rich-media artifact surface — the client half of the `/media` routes.
 *
 * Mirrors the node-render contract on purpose (see `api/nodes.ts`): enqueue returns `202`
 * with an id, the row is polled while `pending|running`, and an SSE stream carries live
 * progress. The two live-progress mechanisms are complementary — the list query auto-refetches
 * while any job is in flight (so statuses settle even for jobs nobody is watching), and
 * `useMediaStream` prints the step-by-step narration of the job the user just triggered.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from './client'

// --------------------------------------------------------------------------- //
// Types (match `src/schemas/media.py`)
// --------------------------------------------------------------------------- //

/** The four kinds the course-home overviews panel can generate (`MediaKind` subset). */
export type MediaKind = 'podcast' | 'slides' | 'infographic' | 'video'

/**
 * The four kinds, in the order the studio offers them. The list of *what exists*;
 * what each one *needs* is the backend's `media_requirements` table (`api/setup.ts`),
 * never a second copy here.
 */
export const MEDIA_KINDS: MediaKind[] = ['podcast', 'video', 'infographic', 'slides']

/**
 * Where an artefact is anchored (`MediaScope`): a single `node` (grounded on its own source
 * and referenceable inline by `PodcastPlayer`/`InfographicImage`), the whole `course`, or a
 * node-less `standalone` steered by the note. The backend infers it from `node_id` when
 * omitted, so sending it explicitly only matters to keep node-less scopes node-less.
 */
export type MediaScope = 'node' | 'course' | 'standalone'

/** `MediaArtifactStatus` lifecycle: the runner walks pending -> running -> done|error. */
export type MediaStatus = 'pending' | 'running' | 'done' | 'error'

/** One artifact as the client may see it (`MediaArtifactRead`). No `asset_path`. */
export interface MediaArtifactRead {
  id: string
  course_id: string
  node_id: string | null
  kind: string
  status: string
  spec_json: Record<string, unknown>
  has_asset: boolean
  content_hash: string | null
  /**
   * The server's stable failure code (`services/media/jobs.py`). What the UI keys its
   * message off — `error` is the English fallback sentence beside it, not copy.
   */
  error_code: string | null
  error: string | null
  created_at: string
  updated_at: string
}

/** `202` from enqueue: the row exists and a background job is running. */
export interface MediaArtifactAccepted {
  artifact_id: string
  status: string
}

// --------------------------------------------------------------------------- //
// Query keys
// --------------------------------------------------------------------------- //

export const courseArtifactsKey = (
  courseId: string | undefined,
  includeNodes = false,
) => ['media', 'course', courseId, includeNodes ? 'all' : 'course-level'] as const

export const mediaArtifactKey = (artifactId: string | undefined) =>
  ['media', 'artifact', artifactId] as const

// --------------------------------------------------------------------------- //
// List + create
// --------------------------------------------------------------------------- //

/** True while a job has not reached a terminal state. */
function isInFlight(status: string): boolean {
  return status === 'pending' || status === 'running'
}

/**
 * `GET /media/artifacts?course_id=…` — every artifact of a course, newest first.
 *
 * Refetches every 2 s while any artifact is `pending|running`, then stops — the documented
 * "poll while in flight" half of the media UX. So even a job the user is not actively
 * streaming settles its status in the list on its own.
 */
export function useCourseArtifacts(
  courseId: string | undefined,
  options: { includeNodes?: boolean } = {},
) {
  const { includeNodes = false } = options
  return useQuery({
    queryKey: courseArtifactsKey(courseId, includeNodes),
    queryFn: () =>
      get<MediaArtifactRead[]>(
        `/media/artifacts?course_id=${courseId}${includeNodes ? '&include_nodes=true' : ''}`,
      ),
    enabled: !!courseId,
    refetchInterval: (query) => {
      const data = query.state.data as MediaArtifactRead[] | undefined
      return data?.some((a) => isInFlight(a.status)) ? 2000 : false
    },
  })
}

/** `POST /media/artifacts` — enqueue one generation job. Returns `202 {artifact_id, status}`. */
export function useCreateArtifact() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      course_id: string
      kind: MediaKind
      node_id?: string
      /** Generation mode. Omit to let the backend infer it from `node_id`. */
      scope?: MediaScope
      /** Free-text personalization instruction, folded into the generator's steering. */
      note?: string
      spec?: Record<string, unknown>
    }) =>
      post<MediaArtifactAccepted>('/media/artifacts', {
        course_id: body.course_id,
        kind: body.kind,
        node_id: body.node_id,
        scope: body.scope,
        note: body.note,
        spec: body.spec ?? { language: 'es' },
      }),
    onSuccess: (_data, vars) => {
      // Both list variants (course-level and include-nodes) share the ['media','course',id]
      // prefix; invalidate the prefix so a node-scoped generation refreshes the studio list.
      queryClient.invalidateQueries({ queryKey: ['media', 'course', vars.course_id] })
    },
  })
}

/** One on-demand runtime result; polls only while its background job is active. */
export function useMediaArtifact(artifactId: string | undefined) {
  return useQuery({
    queryKey: mediaArtifactKey(artifactId),
    queryFn: () => get<MediaArtifactRead>(`/media/artifacts/${artifactId}`),
    enabled: !!artifactId,
    refetchInterval: (query) => {
      const data = query.state.data as MediaArtifactRead | undefined
      return data && isInFlight(data.status) ? 1000 : false
    },
  })
}

// --------------------------------------------------------------------------- //
// SSE progress stream (media:{artifact_id})
// --------------------------------------------------------------------------- //

export type MediaStreamStatus = 'idle' | 'streaming' | 'done' | 'error'

export interface MediaStreamState {
  status: MediaStreamStatus
  /** The generator's current step (`running`, `grounded`, `guion`, `voz`, `listo`, …). */
  step: string | null
  /** The artifact this stream is following, from `media_done`. */
  artifactId: string | null
  /** The failure code from `media_error`. The wording is the UI's — see `lib/mediaErrors`. */
  errorCode: string | null
}

const IDLE_STREAM: MediaStreamState = {
  status: 'idle',
  step: null,
  artifactId: null,
  errorCode: null,
}

/** Events after which the server closes the stream. */
const TERMINAL_EVENTS = new Set(['media_done', 'media_error'])

export interface MediaStreamHandlers {
  /** Fired once, on the first terminal event. */
  onSettled?: (outcome: { reason: 'done' | 'error'; artifactId: string | null }) => void
}

/**
 * Consume `GET /media/artifacts/{id}/stream`.
 *
 * `fetch` + `ReadableStream` rather than `EventSource`, exactly like `useNodeRenderStream`:
 * `EventSource` cannot send the auth cookie cleanly nor be aborted on demand. Truncation is
 * normal — the buffer only acts on complete lines and a bad `JSON.parse` skips the line.
 */
export function useMediaStream(handlers: MediaStreamHandlers = {}) {
  const [state, setState] = useState<MediaStreamState>(IDLE_STREAM)
  const abortRef = useRef<AbortController | null>(null)
  const settledRef = useRef(false)
  const handlersRef = useRef(handlers)
  handlersRef.current = handlers

  const stop = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
  }, [])

  // Leaving the surface stops paying for a stream nobody will read.
  useEffect(() => () => abortRef.current?.abort(), [])

  const start = useCallback(async (artifactId: string) => {
    if (!artifactId) return
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    settledRef.current = false
    setState({ ...IDLE_STREAM, status: 'streaming' })

    const settle = (reason: 'done' | 'error', id: string | null) => {
      if (settledRef.current) return
      settledRef.current = true
      handlersRef.current.onSettled?.({ reason, artifactId: id })
    }

    try {
      const res = await fetch(`/api/v1/media/artifacts/${artifactId}/stream`, {
        credentials: 'include',
        headers: { Accept: 'text/event-stream' },
        signal: controller.signal,
      })
      if (!res.ok || !res.body) {
        // No stream to read; the job may still run server-side. The list poll settles it.
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
        buffer = lines.pop() ?? ''

        let terminal = false

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
            eventType = ''
            continue
          }

          const type = eventType
          eventType = ''

          if (type === 'media_step') {
            setState((prev) => ({
              ...prev,
              step: typeof data.step === 'string' ? data.step : prev.step,
            }))
          } else if (type === 'media_done') {
            const id = typeof data.artifact_id === 'string' ? data.artifact_id : artifactId
            setState((prev) => ({ ...prev, status: 'done', step: 'listo', artifactId: id }))
            settle('done', id)
            terminal = true
          } else if (type === 'media_error') {
            // `message` also rides on this event; it is the server's English fallback and
            // deliberately not read here.
            const code = typeof data.code === 'string' && data.code.trim() ? data.code : null
            setState((prev) => ({ ...prev, status: 'error', errorCode: code }))
            settle('error', null)
            terminal = true
          }

          if (type && TERMINAL_EVENTS.has(type)) break
        }

        if (terminal) break
      }
    } catch (err: unknown) {
      if (controller.signal.aborted) return
      if (err instanceof DOMException && err.name === 'AbortError') return
      // A dropped connection is not a failed job: the list poll is the source of truth.
      setState((prev) => (prev.status === 'streaming' ? prev : { ...prev, status: 'streaming' }))
    } finally {
      if (abortRef.current === controller) abortRef.current = null
    }
  }, [])

  const reset = useCallback(() => {
    stop()
    settledRef.current = false
    setState(IDLE_STREAM)
  }, [stop])

  return useMemo(() => ({ ...state, start, stop, reset }), [state, start, stop, reset])
}
