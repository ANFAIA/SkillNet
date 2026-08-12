import { useActivityDefinition } from '../../../api/activities'
import { createActivityHostPorts } from '../../../api/activity-ports'
import {
  DidactComponentMount,
  useOptionalDidactHost,
  validatePublicActivityDefinition,
} from '../../../lib/didact'
import type { DidactHostPorts, DidactValue, EvaluationResult } from '../../../lib/didact'

const ASYNC_EVALUATION_ADAPTERS = new Set([
  'didact.drawing-response',
  'didact.equation-workbench',
  'didact.evidence-annotation',
  'didact.measurement-lab',
])

function honestPorts(componentId: string, ports: DidactHostPorts): DidactHostPorts {
  return {
    persistence: ports.persistence,
    clock: ports.clock,
    ...(ASYNC_EVALUATION_ADAPTERS.has(componentId) ? { evaluation: ports.evaluation } : {}),
    // Asset and simulation endpoints need dedicated rendering/runtime adapters.
    // Their absence intentionally keeps those activities blocked.
  }
}

function evaluationProps(
  activityId: string,
  componentId: string,
  ports: DidactHostPorts,
): Readonly<Record<string, unknown>> {
  const evaluate = ports.evaluation
  const persistence = ports.persistence
  const scope = { organizationId: '', courseId: '', componentId }
  const evaluateSubmission = async (submission: unknown): Promise<Record<string, unknown>> => {
    if (!evaluate) throw new Error('Evaluation unavailable')
    const result: EvaluationResult = await evaluate.evaluate({
      scope,
      componentId,
      attemptId: `${activityId}-${Date.now()}`,
      response: submission as DidactValue,
    })
    return {
      status: result.outcome === 'unscored' ? 'partial' : result.outcome,
      feedback: typeof result.feedback === 'string' ? result.feedback : '',
    }
  }
  const saveState = (state: unknown) => {
    void persistence?.save(scope, 'state', state as DidactValue)
  }

  if (componentId === 'didact.drawing-response') {
    return { evaluate: (strokes: unknown) => evaluateSubmission({ strokes }), onStateChange: saveState }
  }
  if (['didact.equation-workbench', 'didact.evidence-annotation', 'didact.measurement-lab'].includes(componentId)) {
    return { evaluate: (state: unknown) => evaluateSubmission(state), onStateChange: saveState }
  }
  if (componentId === 'didact.concept-map') return { onStateChange: saveState }
  if (componentId === 'didact.self-explanation-prompt') {
    return { onValueChange: (value: string) => saveState({ value }), onSubmit: (value: unknown) => saveState(value) }
  }
  return {}
}

function ActivityStatus({ kind, children }: { kind: string; children: string }) {
  return (
    <div
      className="rounded-lg border border-border bg-bg-subtle px-4 py-3 text-sm text-text-secondary"
      data-didact-activity-status={kind}
      role={kind === 'failed' ? 'alert' : 'status'}
    >
      {children}
    </div>
  )
}

/**
 * The single OpenUI adapter for the complete Didact registry.
 *
 * OpenUI supplies only an opaque activity id and a reviewed component id. The
 * authored definition is fetched from SkillNet and checked before lazy mounting.
 */
export function DidactActivityBlock({
  activityId,
  componentId,
}: {
  activityId: string
  componentId: string
}) {
  const outerPorts = useOptionalDidactHost()
  const httpPorts = createActivityHostPorts(activityId)
  const ports = honestPorts(componentId, { ...httpPorts, ...outerPorts })
  const definition = useActivityDefinition(activityId)

  if (!activityId || !componentId.startsWith('didact.')) {
    return <ActivityStatus kind="failed">La referencia de esta actividad no es válida.</ActivityStatus>
  }
  if (definition.isPending) return <ActivityStatus kind="loading">Cargando actividad…</ActivityStatus>
  if (definition.isError) {
    return <ActivityStatus kind="failed">No se pudo cargar la actividad.</ActivityStatus>
  }

  const validated = validatePublicActivityDefinition(definition.data, activityId, componentId)
  if (!validated.ok) {
    if (validated.reason === 'declined') {
      return <ActivityStatus kind="blocked">Esta actividad no puede ejecutarse con los datos disponibles.</ActivityStatus>
    }
    return <ActivityStatus kind="failed">La definición pública de la actividad no es válida.</ActivityStatus>
  }

  return (
    <DidactComponentMount
      componentId={componentId}
      componentProps={{
        ...validated.componentProps,
        ...evaluationProps(activityId, componentId, ports),
      }}
      ports={ports}
    />
  )
}
