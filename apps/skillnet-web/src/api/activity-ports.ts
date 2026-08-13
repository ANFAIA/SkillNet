import { get, post, put } from './client'
import type {
  DidactHostPorts,
  DidactScope,
  DidactValue,
  AssetReference,
  EvaluationResult,
  ExecutionResult,
  SimulationResult,
} from '../lib/didact/host-ports'

type OperationResponse = {
  status: 'completed' | 'declined'
  result: DidactValue
  decline_reason: string | null
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

/** HTTP implementations remain activity-scoped; no answer data lives in the browser. */
export function createActivityHostPorts(activityId: string): DidactHostPorts {
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
        const response = await post<OperationResponse>(`${path}/evaluate`, { submission: request.response })
        return completed(response) as EvaluationResult
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
