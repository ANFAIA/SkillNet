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
  is_active?: boolean
  // Only on `GET /users?with_groups=true`. `undefined` means the caller did not ask;
  // `[]` means this person is in no group. The people table needs to tell those apart —
  // one is "no column", the other is a dash in the row.
  groups?: UserGroupBrief[]
}

/** A group as it travels on a person's row: enough to name it and to filter by it. */
export interface UserGroupBrief {
  id: string
  name: string
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

export type CourseGenerationState = 'idle' | 'in_progress' | 'failed' | 'complete'

/** How the learner tutor answers inside a course (`courses.tutor_style`). */
export type TutorStyle = 'socratic' | 'direct'

/** `courses.image_source_policy` — the override over the diagram/screenshot rule. */
export type ImageSourcePolicy = 'auto' | 'keep_original' | 'rebuild'

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
  /** Marks the per-org demo course. Read-only; drives the admin preview variant toggle. */
  is_demo?: boolean
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
  /** How the tutor answers inside this course. Auto-detected at creation, editable after. */
  tutor_style?: TutorStyle
  /**
   * What this course does with the images embedded in its source document.
   *
   * `'auto'` is the rule and the default: a diagram is rebuilt as interactive SkillNet
   * content, a screenshot is kept as the original picture (its information is spatial,
   * so prose is strictly worse). The other two are the policy escapes — never asked at
   * creation, only edited afterwards by someone who has seen a lesson.
   */
  image_source_policy?: ImageSourcePolicy
  /**
   * Whether a creation run owns this course, and how the last one ended (migration
   * 0025). Optional and defaulted to `'idle'` server-side, so a course nobody is
   * creating — which is every course made before the column existed — reads `'idle'`.
   *
   * This is what separates "the wizard died half-way through making this" from "somebody
   * saved a draft on purpose". Both used to be `status: 'draft'` with nothing else to
   * tell them apart.
   */
  generation_state?: CourseGenerationState
  /** Short, safe reason the creation run failed. Never a raw exception. */
  generation_error?: string | null
  generation_failed_at?: string | null
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

/**
 * The three values `enrollment_status` actually holds server-side
 * (`models/enrollment.py`). Two names that used to live here were fiction:
 * `'not_started'` (the API sends `'assigned'`) and `'overdue'`, which is never stored —
 * it is derived from `deadline` vs today (`services/org_snapshot.py:150`). A trailing
 * `| string` used to widen this to `string`, so neither lie could ever fail to compile.
 */
export type EnrollmentStatus = 'assigned' | 'in_progress' | 'completed'

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
  overdue_assignments: number
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

/** One node of a dynamic course schema, as served by `GET /courses/{id}/nodes` (§11.3). */
export interface LearningNode {
  id: string
  title: string
  summary: string | null
  criticality: NodeCriticality
  position: number
  state: NodeState
  mastery: number
  /**
   * Done with it — `mastered` **or** worked through to the end. Sent by the server
   * (`services/node_progression`) rather than derived here from `state` and
   * `completed_at`: deriving it in two places is what kept the padlocks and the progress
   * bar disagreeing.
   */
  done: boolean
  /**
   * May this learner open it. Always `true` while progression is linear — a course is a
   * sequence you walk through and mastery does not govern navigation. Replaces
   * `locked`/`locked_by`; see `docs/design/future-progression-modes.md`.
   */
  available: boolean
  /**
   * ISO timestamp of the first time this learner was served this node, `null` when they
   * have never opened it. The only server-side answer to "where was I?": `state` cannot
   * give it, because `learning` needs a graded answer and a prefetch already creates the
   * row as `not_started`. Consumed by `features/resume/selectResumeNode`.
   */
  first_seen_at: string | null
  /**
   * ISO timestamp of the moment this learner reached the end of the node's content,
   * `null` while they have not. A **separate dimension from mastery**: getting to the last
   * screen is not a demonstration, so the server writes this and leaves `state` and
   * `mastery` alone — a node may legitimately read `state: 'not_started'` next to a
   * `completed_at`. What it does move is progress, because the §7.5 count treats a node as
   * done when it is mastered **or** finished. Written by `POST /nodes/{id}/complete`.
   */
  completed_at: string | null
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
  /**
   * `true` when this is a **fallback** shell served only because the node's knowledge
   * pack is not ready yet. The client must show "Preparándose…" and keep polling rather
   * than present `program` as the lesson; it clears once the pack lands and the episode
   * is regenerated. Absent/false on a real lesson or an honest legacy decline.
   */
  preparing?: boolean
}

/** `GET /users/me/learner-profile` (§11.2). `format_vector` and `tutor_notes` stay server-side. */
export interface LearnerProfile {
  role_title: string | null
  sector: string | null
  goal: string | null
  learning_note: string | null
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

/**
 * `POST` / `GET /courses/{id}/schema/finalize` — one poll's worth of "is this course
 * finished being created yet".
 *
 * The run state and the knowledge-pack progress arrive together on purpose: the create
 * wizard needs both on every tick, and asking two endpoints for halves of the same
 * answer is how the two drift apart on screen.
 */
export interface CourseFinalization {
  course_id: string
  generation_state: CourseGenerationState
  generation_error: string | null
  generation_failed_at: string | null
  schema_status: string
  status: CourseStatus
  packs_ready: number
  packs_total: number
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
  /**
   * Where this learner should go now: the first node not yet done, in order. `null` when
   * the course is finished or empty. The server answers it so that the day the answer
   * stops being "the next one" no client has to change.
   *
   * Not the same question as "where did I leave off", which is `selectResumeNode` over
   * `first_seen_at` — the deepest node actually opened. Both are legitimate and they
   * disagree on purpose.
   */
  next_node_id: string | null
  /** §7.5: every non-archived node done (`mastered` or finished). */
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
 * `QuizItemBlock`): it adds `show_worked_solution`, the flag that says the fourth
 * failure after three hints has arrived, so the item closes with the solution on screen
 * and the learner moves on.
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

/**
 * `POST /nodes/{node_id}/complete` — `NodeCompletionRead`.
 *
 * It answers with the **course** verdict, not just the node's: the reason the endpoint
 * exists is the number on the course progress bar, so one round trip stamps the node and
 * hands back the recomputed percentage. The client derives nothing and cannot paint a
 * stale figure next to a node it has just finished.
 *
 * `state` and `mastery` are echoes of columns the route does not write. Reading
 * `state: 'not_started'` next to a `completed_at` is the two dimensions doing their two
 * different jobs, not an inconsistency.
 */
export interface NodeCompletion {
  node_id: string
  /** Never `null` in a response: by the time it answers, the stamp is there. */
  completed_at: string
  state: NodeState
  mastery: number
  /** The §7.5 course verdict, already recomputed after the stamp. */
  progress_percent: number
  can_complete: boolean
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
  waived_by: string | null
  waived_at: string | null
  active_render_id: string | null
}
