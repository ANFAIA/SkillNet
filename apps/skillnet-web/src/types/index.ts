// TypeScript interfaces matching the SkillNet backend API contract (v1).
// These are kept separate from the legacy mock-data types in src/data/*.

export type UserRole = 'admin' | 'employee'

export interface User {
  id: string
  email: string
  full_name: string
  role: UserRole
  learning_profile?: Record<string, unknown> | null
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
