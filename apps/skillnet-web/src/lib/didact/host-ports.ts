/** JSON-compatible values exchanged with Didact adapters. */
export type DidactValue =
  | null
  | boolean
  | number
  | string
  | DidactValue[]
  | { [key: string]: DidactValue }

export type DidactScope = {
  organizationId: string
  courseId: string
  learnerId?: string
  nodeId?: string
  sessionId?: string
}

export type EvaluationRequest = {
  scope: DidactScope
  componentId: string
  attemptId: string
  response: DidactValue
  rubric?: DidactValue
}

/**
 * A solution the SERVER already wrote out, ready to print.
 *
 * The client never assembles one. Building a solution means reading an answer key, and a
 * client that could read the answer key would not need to be told the solution — the same
 * rule the hint ladder lives by (`components/courses/blocks/QuizItemHints.tsx`).
 */
export type EvaluationSolution = {
  solution: string
  explanation?: string | null
}

export type EvaluationResult = {
  outcome: 'correct' | 'incorrect' | 'partial' | 'unscored'
  score?: number
  maxScore?: number
  feedback?: DidactValue
  /**
   * The server closing the item and handing over the solution (§7.4 rule 8).
   *
   * NEVER inferred here: only the server counts attempts, so only the server can decide
   * the learner has run out of them.
   */
  showWorkedSolution?: boolean
  /** Mastery state as the server keeps it (`learning`, `mastered`…). Display only. */
  state?: string
  mastery?: number
  /** Populated together with `showWorkedSolution`. */
  solution?: EvaluationSolution | null
}

/**
 * The activity cannot be graded at all — a missing answer key, a grader that refuses the
 * definition.
 *
 * It is a different thing from a request that failed, and the difference is the whole
 * point: a failed request is worth retrying, and this is not. No attempt at this activity
 * will ever be scored, so the learner is told once and let out instead of being offered a
 * retry that can only ever be answered by another retry.
 */
export class ActivityNotEvaluableError extends Error {
  readonly reason: string

  constructor(reason: string) {
    super(reason || 'activity cannot be evaluated')
    this.name = 'ActivityNotEvaluableError'
    this.reason = reason
  }
}

export interface EvaluationPort {
  evaluate(request: EvaluationRequest, signal?: AbortSignal): Promise<EvaluationResult>
}

export const DIDACT_EVENT_TYPES = [
  'started',
  'attempted',
  'answered',
  'feedback_viewed',
  'completed',
] as const

export type DidactEventType = (typeof DIDACT_EVENT_TYPES)[number]

export type DidactEventPayload = {
  attemptId?: string
  outcome?: 'correct' | 'incorrect' | 'partial' | 'unscored'
  score?: number
  durationMs?: number
}

export type DidactEvent = {
  version: 1
  eventId: string
  activityId: string
  type: DidactEventType
  occurredAt: string
  scope: DidactScope
  componentId: string
  payload?: DidactEventPayload
}

export interface EventPort {
  emit(event: DidactEvent, signal?: AbortSignal): Promise<void>
}

export interface PersistencePort {
  load(scope: DidactScope, key: string, signal?: AbortSignal): Promise<DidactValue | undefined>
  save(scope: DidactScope, key: string, value: DidactValue, signal?: AbortSignal): Promise<void>
  remove(scope: DidactScope, key: string, signal?: AbortSignal): Promise<void>
}

export type AssetReference = {
  ref: string
  url: string
  mimeType: string
  alt: string
  longDescription?: string
  width?: number
  height?: number
  durationMs?: number
  transcript?: DidactValue[]
  captions?: DidactValue[]
}

export interface AssetPort {
  resolve(assetId: string, scope: DidactScope, signal?: AbortSignal): Promise<AssetReference>
}

export type MediaRequest = {
  scope: DidactScope
  kind: 'image' | 'audio' | 'video'
  prompt: string
  alt?: string
  constraints?: DidactValue
}

export interface MediaPort {
  create(request: MediaRequest, signal?: AbortSignal): Promise<AssetReference>
}

export type ExecutionRequest = {
  scope: DidactScope
  language: string
  source: string
  stdin?: string
  limits?: {
    timeoutMs?: number
    memoryMb?: number
  }
}

export type ExecutionResult = {
  status: 'completed' | 'failed' | 'timed_out'
  stdout: string
  stderr: string
  exitCode?: number
}

export interface ExecutionPort {
  execute(request: ExecutionRequest, signal?: AbortSignal): Promise<ExecutionResult>
}

export type SimulationRequest = {
  scope: DidactScope
  simulationId: string
  state: DidactValue
  action: DidactValue
}

export type SimulationResult = {
  state: DidactValue
  effects?: DidactValue[]
  completed?: boolean
}

export interface SimulationPort {
  transition(request: SimulationRequest, signal?: AbortSignal): Promise<SimulationResult>
}

export type ProgressRecord = {
  scope: DidactScope
  componentId: string
  status: 'not_started' | 'in_progress' | 'completed'
  progress?: number
  evidence?: DidactValue
}

export interface ProgressPort {
  read(scope: DidactScope, componentId: string, signal?: AbortSignal): Promise<ProgressRecord | undefined>
  write(record: ProgressRecord, signal?: AbortSignal): Promise<void>
}

export interface ClockPort {
  now(): Date
}

export type ScheduledTask = {
  id: string
  runAt: Date
  payload: DidactValue
}

export interface SchedulerPort {
  schedule(task: ScheduledTask, signal?: AbortSignal): Promise<void>
  cancel(taskId: string, signal?: AbortSignal): Promise<void>
}

export const DIDACT_HOST_CAPABILITIES = [
  'evaluation',
  'events',
  'persistence',
  'assets',
  'media',
  'execution',
  'simulation',
  'progress',
  'clock',
  'scheduler',
] as const

export type DidactHostCapability = (typeof DIDACT_HOST_CAPABILITIES)[number]

/** Ports supplied by SkillNet. Missing keys represent unavailable capabilities. */
export type DidactHostPorts = {
  evaluation?: EvaluationPort
  events?: EventPort
  persistence?: PersistencePort
  assets?: AssetPort
  media?: MediaPort
  execution?: ExecutionPort
  simulation?: SimulationPort
  progress?: ProgressPort
  clock?: ClockPort
  scheduler?: SchedulerPort
}
