import { ApiError, get, post, put } from './client'
import { ActivityNotEvaluableError } from '../lib/didact/host-ports'
import type {
  DidactHostPorts,
  DidactScope,
  DidactValue,
  AssetReference,
  EvaluationResult,
  EvaluationSolution,
  ExecutionResult,
  SimulationResult,
} from '../lib/didact/host-ports'

type OperationResponse = {
  status: 'completed' | 'declined'
  result: DidactValue
  decline_reason: string | null
}

type ExperienceAttemptResponse = {
  outcome: EvaluationResult['outcome']
  score: number | null
  result: DidactValue
}

type StateResponse = { activity_id: string; state: DidactValue }

type AssetResponse = {
  ref: string
  url: string
  mime_type: string
  alt: string
  long_description?: string
  width?: number
  height?: number
  duration_ms?: number
  transcript?: DidactValue[]
  captions?: DidactValue[]
}

type DidactEventWireEnvelope = {
  version: 1
  event_id: string
  activity_id: string
  component_id: string
  type: string
  occurred_at: string
  payload: {
    attempt_id?: string
    outcome?: string
    score?: number
    duration_ms?: number
  }
}

function completed(response: OperationResponse): DidactValue {
  if (response.status === 'declined') {
    throw new Error(response.decline_reason ?? 'Activity operation declined')
  }
  return response.result
}

function record(value: DidactValue | undefined): Record<string, DidactValue> | undefined {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : undefined
}

/**
 * A solution the server wrote out, or `undefined` when it did not write one.
 *
 * Exported because the shape arrives by two roads — folded into an evaluation result, and
 * on its own from `POST /activities/{id}/solution` when the learner asks for it — and
 * both of them can legitimately carry nothing. `render_solution` returns `None` for an
 * evaluation mode it cannot put into words, so "no solution" is an answer, not a bug, and
 * one function deciding what counts as one keeps the two roads from disagreeing.
 */
export function writtenSolution(value: DidactValue | undefined): EvaluationSolution | undefined {
  const fields = record(value)
  if (!fields || typeof fields.solution !== 'string' || !fields.solution) return undefined
  return {
    solution: fields.solution,
    explanation: typeof fields.explanation === 'string' ? fields.explanation : null,
  }
}

/**
 * Everything the server puts in `result` around the grader's own verdict.
 *
 * This used to keep `feedback` and drop the rest on the floor, which is how a
 * `show_worked_solution` the server had already decided on never reached the screen: the
 * signal arrived in the browser and the client threw it away. Naming each field is
 * deliberate — the wire is snake_case and `EvaluationResult` is not, and a blind spread
 * would leave `show_worked_solution` sitting there unread next to a `showWorkedSolution`
 * nobody set.
 */
function evaluationEnvelope(result: DidactValue): Partial<EvaluationResult> {
  const fields = record(result)
  if (!fields) return {}
  const solution = writtenSolution(fields.solution)
  return {
    ...(fields.feedback === undefined ? {} : { feedback: fields.feedback }),
    ...(fields.show_worked_solution === true ? { showWorkedSolution: true } : {}),
    ...(typeof fields.state === 'string' ? { state: fields.state } : {}),
    ...(typeof fields.mastery === 'number' ? { mastery: fields.mastery } : {}),
    ...(solution === undefined ? {} : { solution }),
  }
}

/**
 * The server saying the activity itself cannot be graded, told apart from a request that
 * merely failed.
 *
 * The two evaluation paths word it differently — `/evaluate` declines the operation with
 * a reason, `/attempts` rejects the submission — so the translation lives here, in one
 * place, and this is the single function to adapt if the backend settles on an explicit
 * flag instead.
 */
function notEvaluable(error: unknown): boolean {
  return (
    error instanceof ApiError
    && error.status === 422
    && error.body.detail.toLowerCase().includes('cannot be evaluated')
  )
}

/** HTTP implementations remain activity-scoped; no answer data lives in the browser. */
export function createActivityHostPorts(
  activityId: string,
  options: { bindingId?: string } = {},
): DidactHostPorts {
  const path = `/activities/${encodeURIComponent(activityId)}`
  return {
    assets: {
      async resolve(assetRef) {
        const response = await get<AssetResponse>(`${path}/assets/${encodeURIComponent(assetRef)}`)
        return {
          ref: response.ref,
          url: response.url,
          mimeType: response.mime_type,
          alt: response.alt,
          longDescription: response.long_description,
          width: response.width,
          height: response.height,
          durationMs: response.duration_ms,
          transcript: response.transcript,
          captions: response.captions,
        } satisfies AssetReference
      },
    },
    events: {
      async emit(event) {
        const body: DidactEventWireEnvelope = {
          version: event.version,
          event_id: event.eventId,
          activity_id: event.activityId,
          component_id: event.componentId,
          type: event.type,
          occurred_at: event.occurredAt,
          payload: {
            ...(event.payload?.attemptId ? { attempt_id: event.payload.attemptId } : {}),
            ...(event.payload?.outcome ? { outcome: event.payload.outcome } : {}),
            ...(event.payload?.score !== undefined ? { score: event.payload.score } : {}),
            ...(event.payload?.durationMs !== undefined ? { duration_ms: event.payload.durationMs } : {}),
          },
        }
        await post<void>(`${path}/events`, body)
      },
    },
    evaluation: {
      async evaluate(request) {
        if (options.bindingId) {
          let response: ExperienceAttemptResponse
          try {
            response = await post<ExperienceAttemptResponse>(`${path}/attempts`, {
              attempt_id: request.attemptId,
              binding_id: options.bindingId,
              submission: request.response,
            })
          } catch (failure) {
            if (notEvaluable(failure)) {
              throw new ActivityNotEvaluableError((failure as ApiError).body.detail)
            }
            throw failure
          }
          return {
            outcome: response.outcome,
            ...(response.score === null ? {} : { score: response.score }),
            ...evaluationEnvelope(response.result),
          }
        }
        const response = await post<OperationResponse>(`${path}/evaluate`, { submission: request.response })
        if (response.status === 'declined') {
          throw new ActivityNotEvaluableError(response.decline_reason ?? '')
        }
        // The verdict (`outcome`, `score`, `maxScore`) is the grader's own and already
        // camelCase; the envelope on top is the server's, and needs translating.
        return { ...(response.result as EvaluationResult), ...evaluationEnvelope(response.result) }
      },
    },
    persistence: {
      async load(_scope, _key) {
        const response = await get<StateResponse>(`${path}/state`)
        return response.state
      },
      async save(_scope, _key, value) {
        await put<StateResponse>(`${path}/state`, { state: value })
      },
      async remove() {
        await put<StateResponse>(`${path}/state`, { state: {} })
      },
    },
    simulation: {
      async transition(request) {
        const response = await post<OperationResponse>(`${path}/transition`, {
          action: request.action,
          state: request.state,
        })
        return completed(response) as SimulationResult
      },
    },
    execution: {
      async execute(request) {
        const response = await post<OperationResponse>(`${path}/execute`, { submission: request })
        return completed(response) as ExecutionResult
      },
    },
    clock: { now: () => new Date() },
    progress: {
      async read() {
        const response = await get<{
          component_id: string
          status: 'not_started' | 'in_progress' | 'completed'
          progress: number
          level: 'beginner' | 'intermediate' | 'advanced'
        }>(`${path}/progress`)
        return {
          scope: { organizationId: '', courseId: '' },
          componentId: response.component_id,
          status: response.status,
          progress: response.progress,
          evidence: { level: response.level },
        }
      },
      async write() {
        throw new Error('progress_is_server_owned')
      },
    },
  }
}

/** Scope helper for component adapters that do not need organization data client-side. */
export function activityScope(nodeId?: string): DidactScope {
  return { organizationId: '', courseId: '', nodeId }
}
