import type {
  DidactHostPorts,
  DidactValue,
  EvaluationResult,
} from '../../../lib/didact'

export async function evaluateDidactSubmission(
  activityId: string,
  componentId: string,
  ports: DidactHostPorts,
  submission: unknown,
): Promise<EvaluationResult> {
  const evaluate = ports.evaluation
  if (!evaluate) throw new Error('Evaluation unavailable')
  const attemptId = crypto.randomUUID()
  const scope = { organizationId: '', courseId: '', componentId }
  await ports.events?.emit({
    version: 1,
    eventId: crypto.randomUUID(),
    activityId,
    type: 'attempted',
    occurredAt: new Date().toISOString(),
    scope,
    componentId,
    payload: { attemptId },
  }).catch(() => undefined)
  const result = await evaluate.evaluate({
    scope,
    componentId,
    attemptId,
    response: { answer: submission } as DidactValue,
  })
  await ports.events?.emit({
    version: 1,
    eventId: crypto.randomUUID(),
    activityId,
    type: 'answered',
    occurredAt: new Date().toISOString(),
    scope,
    componentId,
    payload: {
      attemptId,
      outcome: result.outcome,
      ...(result.score === undefined ? {} : { score: result.score }),
    },
  }).catch(() => undefined)
  await ports.events?.emit({
    version: 1,
    eventId: crypto.randomUUID(),
    activityId,
    type: 'completed',
    occurredAt: new Date().toISOString(),
    scope,
    componentId,
    payload: { attemptId },
  }).catch(() => undefined)
  return result
}

export function evaluationProps(
  activityId: string,
  componentId: string,
  ports: DidactHostPorts,
): Readonly<Record<string, unknown>> {
  const persistence = ports.persistence
  const scope = { organizationId: '', courseId: '', componentId }
  const evaluateSubmission = async (submission: unknown): Promise<Record<string, unknown>> => {
    const result = await evaluateDidactSubmission(activityId, componentId, ports, submission)
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
