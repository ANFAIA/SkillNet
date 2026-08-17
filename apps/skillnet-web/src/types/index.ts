// TypeScript interfaces matching the SkillNet backend API contract (v1).
// These are kept separate from the legacy mock-data types in src/data/*.

// v2 render contract. Type-only imports, so they are erased at build time and no
// import cycle exists at runtime.
import type { UiFormat as UiFormatType } from './node-render'

export type UserRole = 'admin' | 'employee'

// How this deployment is used. Fixed per deployment (see audience-modes.md), it
// arrives on `/auth/me` so the SPA can derive navigation without a second call.
// A UX signal only — the API still enforces access server-side.
export type WorkspaceMode = 'organization' | 'individual'

export interface User {
  id: string
  email: string
  full_name: string
  role: UserRole
  // Present on the `/auth/me` payload (MeRead). Absent on other user payloads
  // (list, detail), so treat it as optional and default to 'organization'.
  workspace_mode?: WorkspaceMode
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
  /**
   * `'uploaded'` is the company's own material. `'generated'` means the model wrote it
   * from a one-line idea in the "desde cero" path, so a course standing on it carries
   * the model's knowledge and not the organisation's policy. Shown, never hidden.
   */
  origin: 'uploaded' | 'generated' | string
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
  /** Optional administrative location. It does not affect delivery or permissions. */
  folder_id?: string | null
  folder_name?: string | null
  created_at: string
  updated_at?: string
  module_count: number
  node_count: number | null
  schema_status: string | null
  /**
   * The **effective** delivery path (§11.3), computed server-side by `resolve_delivery`.
   *
   * Not the raw `courses.delivery_mode` column: the server folds in the feature flag and
   * the schema gate first, so with dynamic courses off — or with the schema still in
   * draft — every course reads `'static'` here and no v1 screen changes. That is what
   * makes it safe for `pages/admin/Content.tsx` to branch on it directly.
   */
  delivery_mode: CourseDeliveryMode
  artifact_generate_policy?: 'admin' | 'everyone' | 'selected'
  artifact_generator_ids?: string[]
  can_generate_artifacts?: boolean
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
  /**
   * Same effective value as `CourseRead.delivery_mode`, repeated here because an
   * employee has no access to `GET /courses` (admin only) — the enrollment is the only
   * place their own screens can read it from.
   */
  delivery_mode: CourseDeliveryMode
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

/**
 * Where an answer came from, decided by the server's grounding ladder
 * (`src/services/retrieval.py`) and never by the model.
 *
 * - `chunks` — retrieved passages of a company document, found by vector search.
 * - `chunks_fts` — the same thing, found by Spanish full-text search instead. A
 *   separate value rather than a reuse of `chunks`, because this label is the
 *   *guarantee* of provenance — the one thing about an answer the model cannot
 *   influence — and collapsing two retrievers into one name would make it claim a
 *   semantic match where there was a lexical one. It is also the rung that runs
 *   whenever no real embedding provider is configured, which is the local default.
 * - `document` — the whole document of one of the learner's courses. A real
 *   answer, but not a located passage, and the UI says so.
 * - `general` — nothing in the company's material covers it. The tutor answers
 *   anyway, from general knowledge, and this is the label that keeps that honest.
 */
export type ChatGrounding = 'chunks' | 'chunks_fts' | 'document' | 'general'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  suggestions?: string[]
  isStreaming?: boolean
  grounding?: ChatGrounding
  /**
   * The answer re-laid in the SkillNet kit, as OpenUI Lang **text**.
   *
   * Always the canonical program re-serialized from a validated `UISpec` on the
   * server — never the model's own bytes. See `UiSpecRenderer`'s `program` prop:
   * the rule is the same one, and a chat answer is a *less* trusted input than a
   * node render, not a more trusted one.
   */
  program?: string
  /** True while the server is laying the answer out. The prose is already complete. */
  isLayingOut?: boolean
  /** True when the model is generating OpenUI Lang directly (single-phase GenUI). */
  generative?: boolean
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

// `LlmSettings` used to live here, as the body of `PUT /settings/llm`. Both are gone:
// the provider is configured in the deployment's `.env`, so there is no request that
// carries a model and an API key from a browser any more.

export interface OrgSettings {
  name: string
  slug: string
  workspace_mode: WorkspaceMode
  self_registration_enabled: boolean
  llm_configured: boolean
  llm_model?: string | null
  embedding_model?: string | null
  llm_base_url?: string | null
  /**
   * Whether the tutor may lay its answers out in the SkillNet kit instead of plain
   * prose. On unless the admin turned it off. Not a safety net — an answer the gate
   * rejects already falls back to prose on its own — but a choice: an admin whose model
   * is weak at the dialect, or who does not want to pay for a second call per answer,
   * turns it off here.
   */
  chat_generative_ui: boolean
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
  /** Server-owned presentation shell. Missing values are treated as legacy during rollout. */
  shell_mode: 'legacy_stepper' | 'episode'
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

export type KnowledgePackStatus =
  | 'pending'
  | 'ready'
  | 'review_required'
  | 'stale'
  | 'failed'

export interface NodeKnowledgePack {
  id: string
  node_id: string
  status: KnowledgePackStatus
  generator_version: string
  pack_hash: string | null
  markdown: string | null
  atom_count: number
  invariant_count: number
  required_evidence_count: number
  blocking_gaps: string[]
  input_tokens: number | null
  output_tokens: number | null
  duration_ms: number | null
  error_message: string | null
  updated_at: string
}

export interface CourseKnowledgePacks {
  course_id: string
  schema_version: number
  nodes: NodeKnowledgePack[]
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
