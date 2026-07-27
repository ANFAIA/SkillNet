// TypeScript interfaces matching the SkillNet backend API contract (v1).
// These are kept separate from the legacy mock-data types in src/data/*.

// v2 render contract. Type-only imports, so they are erased at build time and no
// import cycle exists at runtime. `BloomLevel` now comes from the UI Kit schemas,
// which are the frontend's single declaration of the frozen catalogue (§5.3).
import type { BloomLevel as BloomLevelType } from '../components/courses/kit/schemas'
import type { UiFormat as UiFormatType } from './node-render'

export type UserRole = 'admin' | 'employee'

export interface User {
  id: string
  email: string
  full_name: string
  role: UserRole
  // The backend column is the `learning_profile` enum (`src/models/user.py`), not a
  // JSON blob: it is a plain string, non-nullable, defaulting to 'standard'. The
  // previous `Record<string, unknown> | null` made the onboarding wizard unable to
  // send it at all (§13, B8).
  learning_profile?: 'standard' | 'focus' | 'fast'
  org_id?: string | null
  accessibility?: Record<string, unknown> | null
  hired_at?: string | null
}

export interface Paginated<T> {
  items: T[]
  total: number
  offset: number
  limit: number
}

// --- Documents ---

export type DocumentStatus =
  | 'uploaded'
  | 'processing'
  | 'processed'
  | 'ready'
  | 'failed'

export interface DocumentRead {
  id: string
  title: string
  file_type: string
  page_count: number | null
  size_bytes: number
  status: DocumentStatus | string
  error_message: string | null
  created_at: string
}

// --- Courses / Modules / Lessons / Exercises ---

export type CourseStatus = 'draft' | 'published' | 'archived' | string

export interface CourseRead {
  id: string
  title: string
  description: string | null
  outcome: string | null
  status: CourseStatus
  source_document_id: string | null
  created_at: string
  module_count: number
}

export type ExerciseType =
  | 'test'
  | 'true_false'
  | 'fill_blank'
  | 'order_steps'
  | 'practical_case'
  | 'dialogue'

// Exercise.content is a jsonb payload whose shape depends on the type.
export interface TestContent {
  question: string
  options: string[]
  correct: number
  explanation?: string
}

export interface TrueFalseContent {
  statement: string
  correct: boolean
  explanation?: string
}

export interface FillBlankContent {
  template: string
  blanks: string[]
  explanation?: string
}

export interface OrderStepsContent {
  instruction: string
  steps: string[]
  correct_order: number[]
  explanation?: string
}

export interface PracticalCaseContent {
  context: string
  question: string
}

export interface DialogueContent {
  context: string
}

export type ExerciseContent =
  | TestContent
  | TrueFalseContent
  | FillBlankContent
  | OrderStepsContent
  | PracticalCaseContent
  | DialogueContent

export interface Exercise {
  id: string
  type: ExerciseType
  content: ExerciseContent
  position: number
}

export interface Lesson {
  id: string
  title: string
  content: string // markdown
  position: number
  exercises: Exercise[]
}

export interface Module {
  id: string
  title: string
  summary: string | null
  position: number
  lessons: Lesson[]
}

export interface CourseDetail extends CourseRead {
  modules: Module[]
}

// --- Exercise attempts ---

export interface AttemptResult {
  score: number
  passed: boolean
  feedback: string
  explanation: string
}

export interface CorrectResult extends AttemptResult {
  correct_answer: Record<string, unknown>
}

export interface AttemptRead extends AttemptResult {
  id: string
  exercise_id: string
  attempted_at: string
}

// Type-specific answer payloads (sent as { answer }).
export type TestAnswer = { selected: number }
export type TrueFalseAnswer = { answer: boolean }
export type FillBlankAnswer = { answers: string[] }
export type OrderStepsAnswer = { order: number[] }
export type PracticalCaseAnswer = { response: string }
export type DialogueAnswer = { messages: Array<{ role: string; content: string }> }

export type ExerciseAnswer =
  | TestAnswer
  | TrueFalseAnswer
  | FillBlankAnswer
  | OrderStepsAnswer
  | PracticalCaseAnswer
  | DialogueAnswer

// --- Course Progress ---

export interface LessonProgress {
  lesson_id: string
  completed: boolean
  locked: boolean
  exercises_pending: number
  exercises_total: number
  exercises_passed: number
}

export interface CourseProgress {
  lessons: LessonProgress[]
  can_complete: boolean
  progress_percent: number
}

// --- Enrollments ---

export type EnrollmentStatus =
  | 'not_started'
  | 'in_progress'
  | 'completed'
  | 'overdue'
  | string

export interface EnrollmentRead {
  id: string
  course_id: string
  user_id: string
  status: EnrollmentStatus
  deadline: string | null
  score: number | null
  progress: number | null
  course_title: string
  started_at: string | null
  completed_at: string | null
}

// --- User Skills ---

export interface UserSkillRead {
  id: string
  skill_id: string
  skill_name: string
  level: 'low' | 'medium' | 'high'
  source: string
  last_assessed_at: string | null
}

// --- Chat ---

export interface Citation {
  document: string
  section: string
  page?: number
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  suggestions?: string[]
  isStreaming?: boolean
}

export interface ChatSessionRead {
  id: string
  title: string | null
  agent_type: string
  created_at: string
  updated_at: string
}

export interface ChatMessageRead {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
  metadata?: Record<string, unknown>
}

// --- Generation jobs ---

export type GenerationStep =
  | 'pending'
  | 'extracting'
  | 'structuring'
  | 'generating'
  | 'reviewing'
  | 'published'
  | 'failed'

export interface GenerationJob {
  id: string
  status: GenerationStep
  output_type: string
  progress: Record<string, unknown>
  result_course_id: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface GenerationProgress {
  step: GenerationStep
  message?: string
  courseId?: string
  error?: string
}

// --- Settings ---

export interface LlmSettings {
  model: string
  base_url?: string
  api_key?: string
}

export interface OrgSettings {
  name: string
  slug: string
  self_registration_enabled: boolean
  llm_configured: boolean
  llm_model?: string | null
  embedding_model?: string | null
  llm_base_url?: string | null
}

export interface LlmTestResult {
  ok: boolean
  detail?: string | null
  model?: string | null
}

// --- Dashboard Stats ---

export interface RecentActivityItem {
  type: string
  user_name: string | null
  course_title: string | null
  at: string
}

export interface StatsResponse {
  total_employees: number
  active_employees: number
  total_courses: number
  published_courses: number
  draft_courses: number
  total_enrollments: number
  completed_enrollments: number
  in_progress_enrollments: number
  avg_score: number | null
  recent_activity: RecentActivityItem[]
}

// --- Dynamic courses (v2) ---
// Additive only. No v1 type above changes shape, so `CourseView` and every
// other v1 screen keeps compiling with the feature flag off (§10.1).

export type NodeCriticality = 'critical' | 'recommended' | 'contextual'

export type NodeState =
  | 'not_started'
  | 'probing'
  | 'learning'
  | 'mastered'
  | 'needs_review'

/** One node of a dynamic course schema, as served by `GET /courses/{id}/nodes` (§11.3). */
export interface LearningNode {
  id: string
  title: string
  summary: string | null
  criticality: NodeCriticality
  position: number
  state: NodeState
  mastery: number
  locked: boolean
  /** Ids of the unmet prerequisites that keep this node locked. */
  locked_by: string[]
  /** `state === 'needs_review'` (§7.4). */
  needs_practice: boolean
  estimated_minutes: number
}

/** `GET /nodes/{node_id}/render` (§11.3). `answer_key` is never serialized here. */
export interface NodeRender {
  render_id: string
  node_id: string
  ui_format: UiFormatType
  status: 'pending' | 'generating' | 'ready' | 'failed' | 'fallback'
  backend: string
  cached: boolean
  /**
   * The lesson as OpenUI Lang **text**, re-serialized by the backend from the
   * already-validated `UISpec` (`RenderBackend.serialize`). It replaces the `spec`
   * JSON: the browser now renders the dialect with OpenUI's own runtime, so the
   * flat IR never crosses the wire.
   *
   * It must NEVER be `node_renders.raw_dsl`. The raw model output is
   * attacker-influenced text (a poisoned source document is the path) and feeding
   * it to a reactive runtime bypasses every barrier at once; a `UISpec` cannot
   * represent an AST, so the round-trip through it is a structural guarantee.
   * `raw_dsl` stays in the model and in no response schema.
   */
  program: string
}

/** `GET /users/me/learner-profile` (§11.2). `format_vector` and `tutor_notes` stay server-side. */
export interface LearnerProfile {
  role_title: string | null
  sector: string | null
  goal: string | null
  experience_level: 'unknown' | 'none' | 'some' | 'experienced'
  preset: 'standard' | 'focus' | 'fast'
  nodes_completed: number
  onboarding_completed_at: string | null
  onboarding_skipped: boolean
  calibrating: boolean
}

/** One pre-assessment item from `POST /nodes/{node_id}/probe` (§7.1). Never carries the answer. */
export interface ProbeItem {
  item_id: string
  item_type: ExerciseType
  bloom_level: BloomLevelType
  question: string
  options?: string[]
}

// --- Course schema, design time (admin, §3.2 / §11.1) ---

export type CourseSchemaStatus = 'draft' | 'proposed' | 'validated' | 'archived'

export type CourseDeliveryMode = 'static' | 'dynamic'

/**
 * One node of the schema as the admin surface serves it (`CourseNodeRead`, §11.1).
 *
 * `probe_items` and `probe_answer_key` are deliberately absent: the pre-assessment is
 * pre-generated server-side at validation time and the answer key never leaves the
 * server (§5.2 rule 5).
 */
export interface CourseSchemaNode {
  id: string
  title: string
  summary: string
  outcome: string | null
  criticality: NodeCriticality
  position: number
  mastery_threshold: number
  estimated_minutes: number | null
  default_ui_format: UiFormatType
  skill_id: string | null
  seed_lesson_id: string | null
  source_document_id: string | null
  /** Headings, not chunk ids: chunks die on re-ingest, headings survive (§3.2). */
  source_headings: string[]
  prerequisite_node_ids: string[]
  /** `null` means "no human signed this off", so the node can never be served (§11.1). */
  reviewed_at: string | null
  reviewed_by: string | null
  archived: boolean
}

/** `GET /courses/{course_id}/schema` — `CourseSchemaRead` of §11.1. */
export interface CourseSchema {
  course_id: string
  schema_status: CourseSchemaStatus
  schema_version: number
  delivery_mode: CourseDeliveryMode
  intent_density: number
  validated_by: string | null
  validated_at: string | null
  warnings: string[]
  nodes: CourseSchemaNode[]
}

/**
 * One node of a `PUT /courses/{id}/schema` payload. The PUT is a **full
 * replacement**, never a partial patch: order and the prerequisite graph have to be
 * validated as a whole, and a patch cannot say "this node is gone".
 *
 * `id` absent means "create this node". A node created by this very request cannot
 * yet be anybody's prerequisite — real uuids only — so brand-new edges between two
 * brand-new nodes need a second PUT.
 */
export interface CourseSchemaNodeInput {
  id?: string
  title: string
  summary: string
  outcome: string | null
  criticality: NodeCriticality
  position: number
  mastery_threshold: number
  estimated_minutes: number | null
  default_ui_format: UiFormatType
  skill_id: string | null
  seed_lesson_id: string | null
  source_document_id: string | null
  source_headings: string[]
  prerequisite_node_ids: string[]
  archived: boolean
}

export interface CourseSchemaUpdate {
  intent_density?: number
  nodes: CourseSchemaNodeInput[]
}

/** One blocking rule violation from `422 {"detail": {"code": "schema_invalid", ...}}`. */
export interface SchemaRuleError {
  code: string
  node_ids?: string[]
}

// --- Node runtime, employee (§11.3 / B9) ---
//
// Mirrors `src/schemas/node.py` field for field. Two absences are the contract, not an
// oversight: no `spec`/`ui_spec` anywhere (the browser receives `program`, the dialect
// text re-serialized from the validated IR, §5.1) and no `answer_key` in any shape
// (§5.2 rule 5).

/** `GET /courses/{course_id}/nodes` — `NodeListRead`. */
export interface NodeList {
  course_id: string
  delivery_mode: CourseDeliveryMode
  schema_version: number
  nodes: LearningNode[]
  /** §7.5: every non-archived `critical` node mastered. */
  can_complete: boolean
  blocked_by: string[]
  progress_percent: number
}

/** `202` from `GET /nodes/{node_id}/render`: nothing pinned yet. */
export interface NodeRenderPending {
  /** `pending` = nothing pinned and nothing running; `generating` = a task owns it. */
  status: 'pending' | 'generating'
  request_id: string | null
}

/**
 * `202` from `POST /nodes/{node_id}/render`.
 *
 * `request_id === ''` with `cached: true` means there is no stream: the render was
 * already pinned or the `cache_key` hit. Subscribing then waits on a channel nobody
 * will publish to.
 */
export interface NodeRenderAccepted {
  request_id: string
  cached: boolean
  render_id: string | null
}

/** One entry of `GET /nodes/{node_id}/renders` — the versions this learner was served. */
export interface NodeRenderVersion {
  render_id: string
  created_at: string | null
  ui_format: UiFormatType
  status: NodeRender['status']
}

export interface NodeRenderHistory {
  renders: NodeRenderVersion[]
}

/** One `node_probes` row as the learner may see it. Never carries the answer key. */
export interface ProbeRow {
  id: string
  node_id: string
  schema_version: number
  attempt_no: number
  /** `false` for the diagnostic probe of a declared novice (§7.1): nothing is recorded. */
  scored: boolean
  score: number | null
  mastered: boolean | null
  tiebreak_used: boolean
  created_at: string | null
  completed_at: string | null
}

/**
 * One served probe item, with the fields the constructed tie-break needs.
 *
 * A superset of `ProbeItem` rather than an extension of it: `question` is optional here
 * because a `fill_blank` item carries `template` (the sentence with `___`) and a
 * `practical_case` carries `context` + `question`, so requiring `question` would be a
 * lie for item `c`. The server sends `list[dict]` of answer-free props (`public_props`
 * runs over each one), so the shape is by item type, not uniform.
 */
export interface ProbeItemDetail {
  item_id: string
  item_type: ExerciseType
  bloom_level: BloomLevelType
  question?: string
  options?: string[]
  /** `fill_blank`: the sentence with `___` where the missing piece goes. */
  template?: string
  /** `practical_case`: the situation the question is about. */
  context?: string
}

/** `POST /nodes/{node_id}/probe` — `ProbeSessionRead`. */
export interface ProbeSession {
  /** `null` on the one path with no row to report (past the probe, nothing stored). */
  probe: ProbeRow | null
  items: ProbeItemDetail[]
  reused: boolean
  /** Already decided, when a stored probe is replayed. */
  verdict: string | null
  /** "Vamos a ver que te suena ya" framing: unscored, no failures persisted (§7.1). */
  diagnostic: boolean
}

export interface ProbeAnswerBody {
  probe_id: string
  item_id: string
  answer: unknown
  latency_ms?: number
}

/** `POST /nodes/{node_id}/probe/answer` — `ProbeAnswerResult`. */
export interface ProbeAnswerResult {
  item_id: string
  score: number
  passed: boolean
  /** `null` until every required item is answered. Then `mastered` / `learning` / `tiebreak`. */
  verdict: string | null
  estimate: number | null
  next_item_id: string | null
  /**
   * `"prefetch"` → the **client** fires `POST /render` in the background; that overlap
   * *is* the productive wait of §9.1. `"skip"` → the node was mastered.
   */
  render_hint: 'prefetch' | 'skip' | null
  feedback: string | null
}

/**
 * `POST /nodes/{node_id}/answer` — `NodeAttemptResult`.
 *
 * A superset of `NodeAttemptResult` in `types/node-render.ts` (B6, consumed by
 * `QuizItemBlock`): it adds `show_worked_solution`, the §7.4 flag that says the fourth
 * failure after three hints has arrived and the node is moving to `needs_review`.
 */
export interface NodeAttemptOutcome {
  score: number
  passed: boolean
  feedback: string | null
  /** Only once the item is passed or the **server-side** hint quota is spent. */
  correct_answer: Record<string, unknown> | null
  mastery: number
  state: NodeState
  consecutive_correct: number
  consecutive_failed: number
  next: 'retry' | 'next_item' | 'next_node'
  show_worked_solution: boolean
}

export interface NodeHintResult {
  hint: string
  hints_used: number
  hints_remaining: number
}

export interface NodeFeedbackBody {
  difficulty: 'easy' | 'ok' | 'hard'
  /** Free text, bounded server-side at 1000 chars. One of only two places user text lands. */
  unclear?: string | null
}

/**
 * One instrumentation event (§3.3).
 *
 * `element` is a `format_vector` dimension (`texto` | `ejercicio` | `codigo` | `dato`);
 * anything else is stored and then ignored by the vector. `metadata` is not accepted by
 * the endpoint on purpose: `learning_events.metadata` must never hold user text.
 */
export interface NodeEventInput {
  type:
    | 'view'
    | 'expand'
    | 'scroll_slow'
    | 'scroll_fast'
    | 'quiz_correct'
    | 'quiz_wrong'
    | 'explain_click'
  element?: string
  element_id?: string
  ms?: number
}

/** `POST /nodes/{node_id}/waive` — `NodeStateRead` (admin only, §7.4). */
export interface NodeStateRead {
  node_id: string
  state: NodeState
  mastery: number
  probe_score: number | null
  consecutive_correct: number
  consecutive_failed: number
  hints_used: number
  attempts_count: number
  scaffold_band: 'novice' | 'neutral' | 'advanced'
  needs_practice: boolean
  waived_by: string | null
  waived_at: string | null
  active_render_id: string | null
}
