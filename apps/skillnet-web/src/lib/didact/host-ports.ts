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

export type EvaluationResult = {
  outcome: 'correct' | 'incorrect' | 'partial' | 'unscored'
  score?: number
  maxScore?: number
  feedback?: DidactValue
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
