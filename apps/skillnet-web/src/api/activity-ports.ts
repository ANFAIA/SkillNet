import { get, post, put } from './client'
import type {
  DidactHostPorts,
  DidactScope,
  DidactValue,
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
  }
}

/** Scope helper for component adapters that do not need organization data client-side. */
export function activityScope(nodeId?: string): DidactScope {
  return { organizationId: '', courseId: '', nodeId }
}
