/**
 * Admin course-schema API (§11.1) — the client half of the creator's gate.
 *
 * Three things here are load bearing and not stylistic:
 *
 * 1. **`schema_locked` is surfaced, never swallowed.** `PUT` on a validated course
 *    returns `422 {"detail": {"code": "schema_locked", "message": ...}}`. If the UI
 *    turned that into a generic "error al guardar", the creator would conclude the
 *    save worked or that the app is broken, and the only correct next action
 *    (`POST /schema/unvalidate`, which also drops the course back to
 *    `delivery_mode='static'`) would be invisible. `schemaLockedMessage` pulls the
 *    server's own sentence out so the screen can print it verbatim.
 * 2. **`schema_invalid` errors are structured, not a string.** `schemaRuleErrors`
 *    returns the full list so `SchemaValidationPanel` can name the offending nodes.
 *    The server reports every violation at once on purpose — a creator fixing a
 *    schema wants the whole list, not one error per round trip.
 * 3. **Reviewing is a separate call from saving.** `PUT` clears `reviewed_at` on any
 *    node whose title, summary, criticality or source headings changed (§11.1 rule
 *    2), so "mark reviewed" has its own endpoint and the UI must save first. That
 *    ordering is enforced in the screen, not here.
 *
 * The flag itself is not read here: `api/health.ts` owns `useDynamicCoursesMode`, and
 * `GET /health` is the only route that exposes it (§10.1).
 */

import { useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, get, post, put } from './client'
import type { CourseSchema, CourseSchemaUpdate, SchemaRuleError } from '../types'

export const schemaQueryKey = (courseId: string | undefined) =>
  ['courses', courseId, 'schema'] as const

// --------------------------------------------------------------------------- //
// Error narrowing
// --------------------------------------------------------------------------- //

/**
 * The nested `detail` object of §11.1.
 *
 * `ApiErrorBody.detail` is typed `string` because every v1 route returns a flat
 * message; the schema routes are the exception (FastAPI's default `HTTPException`
 * rendering keeps the dict), so the cast is where the two contracts meet.
 */
function schemaDetail(error: unknown): Record<string, unknown> | null {
  if (!(error instanceof ApiError)) return null
  const detail = (error.body as { detail?: unknown }).detail
  if (detail === null || typeof detail !== 'object' || Array.isArray(detail)) return null
  return detail as Record<string, unknown>
}

/** The server's own `schema_locked` sentence, or `null` if this is another error. */
export function schemaLockedMessage(error: unknown): string | null {
  const detail = schemaDetail(error)
  if (!detail || detail.code !== 'schema_locked') return null
  return typeof detail.message === 'string' && detail.message.trim()
    ? detail.message
    : 'Este esquema esta validado. Sacalo de validacion antes de editarlo.'
}

/** Every blocking rule violation of a `422 schema_invalid`, in server order. */
export function schemaRuleErrors(error: unknown): SchemaRuleError[] {
  const detail = schemaDetail(error)
  if (!detail) return []
  if (detail.code === 'schema_invalid' && Array.isArray(detail.errors)) {
    return detail.errors
      .filter((entry): entry is Record<string, unknown> =>
        entry !== null && typeof entry === 'object',
      )
      .map((entry) => ({
        code: typeof entry.code === 'string' ? entry.code : 'unknown',
        node_ids: Array.isArray(entry.node_ids) ? entry.node_ids.map(String) : undefined,
      }))
  }
  // `node_has_progress` and `unknown_node` are single-code bodies with the same
  // `node_ids` shape, so the panel can render them through the same list.
  if (typeof detail.code === 'string' && detail.code !== 'schema_locked') {
    return [
      {
        code: detail.code,
        node_ids: Array.isArray(detail.node_ids) ? detail.node_ids.map(String) : undefined,
      },
    ]
  }
  return []
}

/** A message for an error that is neither `schema_locked` nor `schema_invalid`. */
export function schemaErrorMessage(error: unknown): string | null {
  if (!error) return null
  if (schemaLockedMessage(error)) return null
  if (schemaRuleErrors(error).length > 0) return null
  if (error instanceof ApiError) {
    const detail = (error.body as { detail?: unknown }).detail
    if (typeof detail === 'string' && detail.trim()) return detail
  }
  return 'No se pudo completar la operacion.'
}

/** With the flag `off` the whole admin surface 404s, indistinguishable from absent. */
export function isSchemaSurfaceDisabled(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404
}

// --------------------------------------------------------------------------- //
// Schema CRUD
// --------------------------------------------------------------------------- //

export function useCourseSchema(courseId: string | undefined) {
  return useQuery({
    queryKey: schemaQueryKey(courseId),
    queryFn: () => get<CourseSchema>(`/courses/${courseId}/schema`),
    enabled: !!courseId,
    retry: false,
  })
}

export function useUpdateCourseSchema(courseId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: CourseSchemaUpdate) =>
      put<CourseSchema>(`/courses/${courseId}/schema`, payload),
    onSuccess: (data) => {
      queryClient.setQueryData(schemaQueryKey(courseId), data)
      // The PUT recomputes enrollment closure (§7.5), so course lists are stale too.
      queryClient.invalidateQueries({ queryKey: ['courses'] })
    },
  })
}

export function useValidateCourseSchema(courseId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => post<CourseSchema>(`/courses/${courseId}/schema/validate`),
    onSuccess: (data) => {
      queryClient.setQueryData(schemaQueryKey(courseId), data)
      queryClient.invalidateQueries({ queryKey: ['courses'] })
      queryClient.invalidateQueries({ queryKey: ['enrollments'] })
    },
  })
}

/**
 * `POST /schema/unvalidate` — the only door back to editing.
 *
 * It is not a soft toggle: the same transaction sets `schema_status='proposed'` **and**
 * `delivery_mode='static'`, so calling it takes a live course out of v2 until someone
 * validates it again. The screen says so before the click.
 */
export function useUnvalidateCourseSchema(courseId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => post<CourseSchema>(`/courses/${courseId}/schema/unvalidate`),
    onSuccess: (data) => {
      queryClient.setQueryData(schemaQueryKey(courseId), data)
      queryClient.invalidateQueries({ queryKey: ['courses'] })
      queryClient.invalidateQueries({ queryKey: ['enrollments'] })
    },
  })
}

export function useProposeCourseSchema(courseId: string | undefined) {
  return useMutation({
    mutationFn: (payload: { source_document_id?: string; intent_density: number }) =>
      post<{ job_id: string }>(`/courses/${courseId}/schema/propose`, payload),
  })
}

export function useMarkNodeReviewed(courseId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (nodeId: string) =>
      post<{ node_id: string; reviewed_at: string | null; reviewed_by: string | null }>(
        `/courses/${courseId}/schema/nodes/${nodeId}/review`,
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: schemaQueryKey(courseId) })
    },
  })
}

// --------------------------------------------------------------------------- //
// Propose job tracking
// --------------------------------------------------------------------------- //

interface SchemaJob {
  id: string
  status: string
  error_message: string | null
}

/** Statuses a schema job can end on. `published` is v1's and cannot happen here. */
const TERMINAL_JOB_STATUSES = new Set(['schema_proposed', 'failed', 'published'])

/**
 * Poll a `schema/propose` job until it lands, then refresh the schema.
 *
 * Polling rather than the SSE stream `api/generation.ts` uses: that hook only knows
 * v1's `step`/`completed`/`error` events and terminates on `completed`, whereas a
 * schema job ends on `schema_ready`. Teaching it a second vocabulary would mean
 * editing a v1 file this batch is not allowed to touch, and a 2 s poll on a job that
 * takes one LLM call is not the bottleneck.
 */
export function useSchemaProposeJob(
  courseId: string | undefined,
  jobId: string | null,
) {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ['generation-jobs', jobId, 'schema'],
    queryFn: () => get<SchemaJob>(`/generation-jobs/${jobId}`),
    enabled: !!jobId,
    retry: false,
    refetchInterval: (q) =>
      q.state.data && TERMINAL_JOB_STATUSES.has(q.state.data.status) ? false : 2000,
  })

  const status = query.data?.status
  const settled = !!status && TERMINAL_JOB_STATUSES.has(status)

  useEffect(() => {
    if (!settled) return
    queryClient.invalidateQueries({ queryKey: schemaQueryKey(courseId) })
  }, [settled, courseId, queryClient])

  return {
    status,
    settled,
    failed: status === 'failed',
    error: query.data?.error_message ?? null,
    running: !!jobId && !settled,
  }
}
