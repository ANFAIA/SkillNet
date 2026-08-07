import { useEffect, useState, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence, LayoutGroup, useInstantLayoutTransition } from 'framer-motion'
import { arrayMove } from '@dnd-kit/sortable'
import { useIntl } from 'react-intl'
import { ease, duration } from '../../lib/motion'
import { Button, Input, Textarea, Badge, EmptyState, FileUploadZone, ProgressBar } from '../../components/ui'
import { GenerationProgress } from '../../components/generation/GenerationProgress'
import { SchemaContent } from '../../components/schema/SchemaContent'
import type { StreamPhase } from '../../components/schema/SchemaContent'
import {
  useUploadDocument,
  useProcessDocument,
  useCreateSourceFromIdea,
  waitForDocumentReady,
} from '../../api/documents'
import { useCreateCourse, useGenerateContent, usePublishCourse, useCourse, useUpdateLesson, useUpdateExercise } from '../../api/courses'
import { useGenerationProgress, useGenerationJobStatus, jobToProgress } from '../../api/generation'
import { streamSchemaProposal } from '../../api/schemaStream'
import { useUsers } from '../../api/users'
import { useAssignCourse } from '../../api/enrollments'
import { ApiError, get, post, put } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import type { GenerationProgress as GenProgress, User, Lesson, Exercise, ExerciseContent } from '../../types'
import type { ProposedNode, Phase, SourceType, DeliveryChoice } from './createCourseTypes'

// ── Icons ────────────────────────────────────────────────────

function FileIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  )
}

function EditIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

function PencilIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
    </svg>
  )
}

function XIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

function SaveIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`transition-transform ${open ? 'rotate-90' : ''}`}
    >
      <polyline points="9 18 15 12 9 6" />
    </svg>
  )
}

function SuccessIcon() {
  return (
    <svg width="56" height="56" viewBox="0 0 56 56" fill="none">
      <circle cx="28" cy="28" r="28" className="fill-accent/10" />
      <circle cx="28" cy="28" r="20" className="fill-accent/20" />
      <path
        d="M20 28.5L25.5 34L36 23"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="text-accent"
      />
    </svg>
  )
}

// ── Small inline components ─────────────────────────────────

function UploadedFileRow({ upload: u, onRemove }: {
  upload: { file: File; status: string; progress: number; error?: string; documentId?: string }
  onRemove: () => void
}) {
  const intl = useIntl()
  return (
    <div className="flex items-center gap-3 border border-border rounded-lg px-3 py-2.5 group">
      <div className="shrink-0 w-8 h-8 rounded bg-bg-muted flex items-center justify-center">
        <FileIcon />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-text truncate">{u.file.name}</p>
        <p className="text-xs text-text-muted">
          {(u.file.size / 1024).toFixed(0)} KB
          {u.status === 'uploading' && ` · ${intl.formatMessage({ id: 'create.uploading' })}`}
          {u.status === 'processing' && ` · ${intl.formatMessage({ id: 'create.processing' })}`}
          {u.status === 'ready' && ` · ${intl.formatMessage({ id: 'create.uploadReady' })}`}
          {u.status === 'error' && ` · ${intl.formatMessage({ id: 'create.uploadError' })}`}
        </p>
        {u.status === 'uploading' && <ProgressBar value={u.progress} size="sm" className="mt-1.5" />}
      </div>
      {(u.status === 'ready' || u.status === 'processing') && (
        <span className="text-accent shrink-0"><CheckIcon /></span>
      )}
      {u.status === 'error' && (
        <span className="text-danger text-xs shrink-0">{u.error}</span>
      )}
      <button
        type="button"
        onClick={onRemove}
        className="text-text-muted hover:text-danger p-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
        title={intl.formatMessage({ id: 'create.removeFile' })}
      >
        <XIcon size={14} />
      </button>
    </div>
  )
}

function DeliverySelector({ value, onChange }: { value: DeliveryChoice; onChange: (v: DeliveryChoice) => void }) {
  const intl = useIntl()
  const options: { key: DeliveryChoice; label: string; desc: string }[] = [
    { key: 'dynamic', label: intl.formatMessage({ id: 'create.deliveryDynamic' }), desc: intl.formatMessage({ id: 'create.deliveryDynamicDesc' }) },
    { key: 'static', label: intl.formatMessage({ id: 'create.deliveryStatic' }), desc: intl.formatMessage({ id: 'create.deliveryStaticDesc' }) },
  ]

  return (
    <div>
      <label className="block text-sm font-medium text-text mb-2">{intl.formatMessage({ id: 'create.deliveryMode' })}</label>
      <div className="grid grid-cols-2 gap-3">
        {options.map((opt) => (
          <button
            key={opt.key}
            type="button"
            onClick={() => onChange(opt.key)}
            className={`text-left border rounded-lg px-4 py-3 transition-colors ${
              value === opt.key
                ? 'border-primary bg-primary-subtle'
                : 'border-border hover:border-border-strong'
            }`}
          >
            <p className="text-sm font-medium text-text">{opt.label}</p>
            <p className="text-xs text-text-muted mt-0.5">{opt.desc}</p>
          </button>
        ))}
      </div>
    </div>
  )
}

// ── Helpers ─────────────────────────────────────────────────

/** Extract a displayable string from a polymorphic exercise content payload. */
function exerciseSummary(content: ExerciseContent): string {
  if ('question' in content && typeof content.question === 'string') return content.question
  if ('statement' in content && typeof content.statement === 'string') return content.statement
  if ('instruction' in content && typeof content.instruction === 'string') return content.instruction
  if ('context' in content && typeof content.context === 'string') return content.context
  return ''
}

// ── Inline editable lesson (unchanged logic) ────────────────

function EditableLesson({ lesson }: { lesson: Lesson }) {
  const intl = useIntl()
  const [editingTitle, setEditingTitle] = useState(false)
  const [editingContent, setEditingContent] = useState(false)
  const [titleDraft, setTitleDraft] = useState(lesson.title)
  const [contentDraft, setContentDraft] = useState(lesson.content)
  const [expanded, setExpanded] = useState(false)
  const updateLesson = useUpdateLesson()

  function saveTitle() {
    if (titleDraft.trim() && titleDraft !== lesson.title) {
      updateLesson.mutate({ lessonId: lesson.id, payload: { title: titleDraft.trim() } })
    }
    setEditingTitle(false)
  }
  function cancelTitle() { setTitleDraft(lesson.title); setEditingTitle(false) }
  function saveContent() {
    if (contentDraft !== lesson.content) {
      updateLesson.mutate({ lessonId: lesson.id, payload: { content: contentDraft } })
    }
    setEditingContent(false)
  }
  function cancelContent() { setContentDraft(lesson.content); setEditingContent(false) }

  return (
    <li className="text-sm border border-border rounded-lg p-3">
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => setExpanded(!expanded)} className="text-text-muted hover:text-text shrink-0">
          <ChevronIcon open={expanded} />
        </button>
        {editingTitle ? (
          <div className="flex items-center gap-1.5 flex-1 min-w-0">
            <input
              className="flex-1 min-w-0 text-sm border border-border rounded px-2 py-1 bg-bg text-text focus:outline-none focus:border-primary"
              value={titleDraft}
              onChange={(e) => setTitleDraft(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') saveTitle(); if (e.key === 'Escape') cancelTitle() }}
              autoFocus
            />
            <button type="button" onClick={saveTitle} className="text-accent hover:text-accent/80 p-0.5" title={intl.formatMessage({ id: 'create.save' })}><SaveIcon /></button>
            <button type="button" onClick={cancelTitle} className="text-text-muted hover:text-text p-0.5" title={intl.formatMessage({ id: 'create.cancel' })}><XIcon /></button>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 flex-1 min-w-0 group">
            <span className="text-text-secondary truncate min-w-0">{lesson.title}</span>
            <button
              type="button"
              onClick={() => { setTitleDraft(lesson.title); setEditingTitle(true) }}
              className="text-text-muted hover:text-primary opacity-0 group-hover:opacity-100 transition-opacity p-0.5 shrink-0"
              title={intl.formatMessage({ id: 'create.editTitle' })}
            >
              <PencilIcon />
            </button>
          </div>
        )}
      </div>
      {expanded && (
        <div className="mt-3 ml-6">
          <div className="mb-2">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-text-muted uppercase tracking-wide">{intl.formatMessage({ id: 'create.contentLabel' })}</span>
              {!editingContent && (
                <button
                  type="button"
                  onClick={() => { setContentDraft(lesson.content); setEditingContent(true) }}
                  className="text-text-muted hover:text-primary p-0.5"
                  title={intl.formatMessage({ id: 'create.editContent' })}
                >
                  <PencilIcon />
                </button>
              )}
            </div>
            {editingContent ? (
              <div>
                <textarea
                  className="w-full text-sm border border-border rounded px-3 py-2 bg-bg text-text focus:outline-none focus:border-primary font-mono min-h-[120px] resize-y"
                  value={contentDraft}
                  onChange={(e) => setContentDraft(e.target.value)}
                  rows={8}
                />
                <div className="flex items-center gap-2 mt-1.5">
                  <Button size="sm" variant="primary" onClick={saveContent} disabled={updateLesson.isPending}>
                    {updateLesson.isPending ? intl.formatMessage({ id: 'create.saving' }) : intl.formatMessage({ id: 'create.save' })}
                  </Button>
                  <Button size="sm" variant="secondary" onClick={cancelContent}>{intl.formatMessage({ id: 'create.cancel' })}</Button>
                </div>
              </div>
            ) : (
              <pre className="text-xs text-text-secondary bg-bg-subtle rounded p-2 whitespace-pre-wrap max-h-40 overflow-y-auto">
                {lesson.content.slice(0, 500)}{lesson.content.length > 500 ? '...' : ''}
              </pre>
            )}
          </div>
          {lesson.exercises.length > 0 && (
            <div>
              <span className="text-xs font-medium text-text-muted uppercase tracking-wide">
                {intl.formatMessage({ id: 'create.exercisesLabel' }, { count: lesson.exercises.length })}
              </span>
              <div className="mt-1 space-y-2">
                {lesson.exercises.map((ex) => <EditableExercise key={ex.id} exercise={ex} />)}
              </div>
            </div>
          )}
        </div>
      )}
    </li>
  )
}

function EditableExercise({ exercise }: { exercise: Exercise }) {
  const intl = useIntl()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(() => JSON.stringify(exercise.content, null, 2))
  const updateExercise = useUpdateExercise()

  function save() {
    try {
      const parsed = JSON.parse(draft)
      updateExercise.mutate({ exerciseId: exercise.id, payload: { content: parsed } })
      setEditing(false)
    } catch { /* invalid JSON */ }
  }
  function cancel() { setDraft(JSON.stringify(exercise.content, null, 2)); setEditing(false) }

  return (
    <div className="border border-border/50 rounded p-2 bg-bg-subtle">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Badge variant="primary" badgeStyle="plain">{exercise.type.replace(/_/g, ' ')}</Badge>
          <span className="text-xs text-text-muted truncate min-w-0">
            {exerciseSummary(exercise.content)}
          </span>
        </div>
        {!editing && (
          <button
            type="button"
            onClick={() => { setDraft(JSON.stringify(exercise.content, null, 2)); setEditing(true) }}
            className="text-text-muted hover:text-primary p-0.5 shrink-0"
            title={intl.formatMessage({ id: 'create.editExercise' })}
          >
            <PencilIcon />
          </button>
        )}
      </div>
      {editing && (
        <div className="mt-2">
          <textarea
            className="w-full text-xs border border-border rounded px-3 py-2 bg-bg text-text focus:outline-none focus:border-primary font-mono min-h-[100px] resize-y"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={6}
          />
          <div className="flex items-center gap-2 mt-1.5">
            <Button size="sm" variant="primary" onClick={save} disabled={updateExercise.isPending}>
              {updateExercise.isPending ? intl.formatMessage({ id: 'create.saving' }) : intl.formatMessage({ id: 'create.save' })}
            </Button>
            <Button size="sm" variant="secondary" onClick={cancel}>{intl.formatMessage({ id: 'create.cancel' })}</Button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Review step ─────────────────────────────────────────────

function StepReview({ courseId, onPublish, publishing, published }: {
  courseId: string
  onPublish: () => void
  publishing: boolean
  published: boolean
}) {
  const intl = useIntl()
  const { data: course, isLoading } = useCourse(courseId)
  if (isLoading) return <p className="text-sm text-text-secondary">{intl.formatMessage({ id: 'create.loading' })}</p>
  if (!course) return <EmptyState title={intl.formatMessage({ id: 'create.loadError' })} />
  const totalLessons = course.modules.reduce((acc, m) => acc + m.lessons.length, 0)
  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-text-secondary">{intl.formatMessage({ id: 'create.modulesLessons' }, { modules: course.modules.length, lessons: totalLessons })}</p>
        <Button size="sm" variant="accent" onClick={onPublish} disabled={publishing || published}>
          {published ? intl.formatMessage({ id: 'create.published' }) : publishing ? intl.formatMessage({ id: 'create.publishing' }) : intl.formatMessage({ id: 'create.publish' })}
        </Button>
      </div>
      <div className="mt-6 space-y-3">
        {course.modules.map((mod, i) => (
          <div key={mod.id} className="border border-border rounded-lg p-5">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-base font-medium text-text truncate min-w-0">{intl.formatMessage({ id: 'create.moduleTitle' }, { num: i + 1, title: mod.title })}</h3>
              <Badge variant="accent" badgeStyle="plain">{intl.formatMessage({ id: 'create.lessonsCount' }, { count: mod.lessons.length })}</Badge>
            </div>
            <ul className="mt-3 space-y-2">
              {mod.lessons.map((l) => <EditableLesson key={l.id} lesson={l} />)}
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Assign step ─────────────────────────────────────────────

function StepAssign({ selected, onToggle, deadline, onDeadline }: {
  selected: Set<string>
  onToggle: (id: string) => void
  deadline: string
  onDeadline: (v: string) => void
}) {
  const intl = useIntl()
  const { data, isLoading } = useUsers({ role: 'employee' })
  const employees: User[] = data?.items ?? []
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div>
        <label className="block text-sm font-medium text-text mb-2">{intl.formatMessage({ id: 'create.employeesLabel' })}</label>
        <div className="border border-border rounded-lg max-h-64 overflow-y-auto">
          {isLoading ? (
            <p className="text-sm text-text-muted p-4">{intl.formatMessage({ id: 'create.loading' })}</p>
          ) : employees.length === 0 ? (
            <p className="text-sm text-text-muted p-4">{intl.formatMessage({ id: 'create.noEmployees' })}</p>
          ) : (
            employees.map((emp) => (
              <label
                key={emp.id}
                className="flex items-center gap-3 px-4 py-2.5 border-b border-border last:border-b-0 hover:bg-bg-subtle cursor-pointer transition-colors"
              >
                <input type="checkbox" checked={selected.has(emp.id)} onChange={() => onToggle(emp.id)} className="accent-primary" />
                <div className="min-w-0">
                  <p className="text-sm text-text truncate">{emp.full_name}</p>
                  <p className="text-xs text-text-muted truncate">{emp.email}</p>
                </div>
              </label>
            ))
          )}
        </div>
        <p className="text-xs text-text-muted mt-1.5">{intl.formatMessage({ id: 'create.selectedCount' }, { count: selected.size })}</p>
      </div>
      <div>
        <Input label={intl.formatMessage({ id: 'create.deadlineLabel' })} type="date" value={deadline} onChange={(e) => onDeadline(e.target.value)} />
      </div>
    </div>
  )
}

// ── Transitions ─────────────────────────────────────────────

const morphTransition = {
  layout: { type: 'spring' as const, stiffness: 200, damping: 28 },
}

// Content inside cards -- opacity only, no blur.
const contentReveal = {
  initial: { opacity: 0 },
  animate: {
    opacity: 1,
    transition: { duration: duration.normal, ease: ease.base, delay: 0.35 },
  },
}

// Inner content swap (details <-> schema) -- opacity only, no blur.
// The delay lets the layout morph spring settle (~350ms) before content fades in.
const innerFadeOut = {
  exit: { opacity: 0, transition: { duration: duration.fast, ease: ease.base } },
}
const innerFadeIn = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: duration.normal, ease: ease.base, delay: 0.35 } },
}

// ── Main component ──────────────────────────────────────────

export function CreateCourse() {
  const intl = useIntl()
  const navigate = useNavigate()
  const { user: currentUser } = useAuth()

  // Phase state
  const [phase, setPhase] = useState<Phase>('choose')
  const [source, setSource] = useState<SourceType>(null)
  const [deliveryChoice, setDeliveryChoice] = useState<DeliveryChoice>('dynamic')
  // Official hook: state changes inside the callback skip layout animation
  const startInstant = useInstantLayoutTransition()

  // Form state
  const [title, setTitle] = useState('')
  const [idea, setIdea] = useState('')
  const [documentId, setDocumentId] = useState<string | null>(null)
  const [writingSource, setWritingSource] = useState(false)
  const [courseId, setCourseId] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [startError, setStartError] = useState<string | null>(null)
  const [published, setPublished] = useState(false)
  const [assignSelected, setAssignSelected] = useState<Set<string>>(new Set())
  const [deadline, setDeadline] = useState('')

  // Created course summary (for the success screen)
  const [createdTitle, setCreatedTitle] = useState('')
  const [createdNodeCount, setCreatedNodeCount] = useState(0)
  const [createdMinutes, setCreatedMinutes] = useState(0)
  const [testingCourse, setTestingCourse] = useState(false)

  // Schema proposal state (streaming)
  const [proposedNodes, setProposedNodes] = useState<ProposedNode[]>([])
  const [proposing, setProposing] = useState(false)
  const [proposeError, setProposeError] = useState<string | null>(null)
  const [density, setDensity] = useState(3)
  const [streamPhase, setStreamPhase] = useState<StreamPhase>('idle')
  const [enrichedNodes, setEnrichedNodes] = useState<Set<number>>(new Set())
  const proposeAbortRef = useRef<AbortController | null>(null)
  const nodeKeyCounter = useRef(0)
  const assignKeys = useCallback(
    (nodes: Omit<ProposedNode, '_key'>[]): ProposedNode[] =>
      nodes.map((n) => ({
        ...n,
        _key: '_key' in n ? (n as ProposedNode)._key : nodeKeyCounter.current++,
      })),
    [],
  )

  // Hooks
  const uploader = useUploadDocument()
  const processDoc = useProcessDocument()
  const createSource = useCreateSourceFromIdea()
  const createCourse = useCreateCourse()
  const generate = useGenerateContent()
  const publish = usePublishCourse()
  const assign = useAssignCourse()

  // Track uploaded document
  const latestUpload = uploader.uploads[uploader.uploads.length - 1]
  useEffect(() => {
    if (latestUpload?.status === 'processing' && latestUpload.documentId && latestUpload.documentId !== documentId) {
      setDocumentId(latestUpload.documentId)
      processDoc.mutate(latestUpload.documentId)
      uploader.markReady(latestUpload.documentId)
    }
  }, [latestUpload, documentId, processDoc, uploader])

  // Auto-suggest title from filename
  useEffect(() => {
    if (source === 'importar' && latestUpload?.file.name && !title) {
      const name = latestUpload.file.name.replace(/\.(pdf|docx|md|txt)$/i, '').replace(/[-_]/g, ' ')
      setTitle(name.charAt(0).toUpperCase() + name.slice(1))
    }
  }, [source, latestUpload, title])

  // Generation tracking
  const { progress: sseProgress, connectionFailed } = useGenerationProgress(phase === 'generating' ? jobId : null)
  const { data: polledJob } = useGenerationJobStatus(phase === 'generating' && connectionFailed ? jobId : null)
  const effective: GenProgress = connectionFailed && polledJob ? jobToProgress(polledJob) : sseProgress

  useEffect(() => {
    if (phase === 'generating' && effective.step === 'published') {
      if (effective.courseId) setCourseId(effective.courseId)
      setPublished(true)
      setPhase('review')
    }
  }, [phase, effective.step, effective.courseId])

  // Schema proposal: two-phase SSE streaming
  const proposeSchema = useCallback((d: number) => {
    proposeAbortRef.current?.abort()

    setProposing(true)
    setProposeError(null)
    setProposedNodes([])
    setStreamPhase('idle')
    setEnrichedNodes(new Set())

    // Track structure nodes by ref so enrichment callbacks can read them
    // without depending on stale closures over proposedNodes.
    const structureRef: { nodes: ProposedNode[] } = { nodes: [] }

    const controller = streamSchemaProposal(
      {
        title: title.trim(),
        description: idea.trim() || undefined,
        intent_density: d,
      },
      {
        onStructure: (nodes) => {
          const proposed = assignKeys(
            nodes.map((n) => ({
              title: n.title,
              summary: '',
              outcome: null,
              criticality: n.criticality || 'recommended',
              default_ui_format: 'explanation',
              estimated_minutes: 10,
              source_headings: [],
              prerequisites: n.prerequisites || [],
            })),
          )
          structureRef.nodes = proposed
          setProposedNodes(proposed)
          setStreamPhase('structure')
        },
        onNodeDetail: (result) => {
          const { index, detail } = result
          setProposedNodes((prev) => {
            const updated = [...prev]
            if (index >= 0 && index < updated.length) {
              updated[index] = {
                ...updated[index],
                summary: detail.summary || updated[index].summary,
                outcome: detail.outcome || updated[index].outcome,
                estimated_minutes: detail.estimated_minutes ?? updated[index].estimated_minutes,
                default_ui_format: detail.default_ui_format || updated[index].default_ui_format,
              }
            }
            return updated
          })
          setEnrichedNodes((prev) => {
            const next = new Set(prev)
            next.add(index)
            return next
          })
          setStreamPhase('enriching')
        },
        onDone: () => {
          setProposing(false)
          setStreamPhase('done')
        },
        onError: (message) => {
          setProposing(false)
          setStreamPhase('idle')
          setProposeError(message)
        },
      },
    )
    proposeAbortRef.current = controller
  }, [title, idea, assignKeys])

  // Auto-propose when entering schema from details -- re-propose if title/idea changed
  const prevPhaseRef = useRef<Phase>('choose')
  const lastProposedInputRef = useRef<{ title: string; idea: string } | null>(null)
  useEffect(() => {
    if (phase === 'schema' && prevPhaseRef.current === 'details') {
      const current = { title: title.trim(), idea: idea.trim() }
      const last = lastProposedInputRef.current
      if (!last || last.title !== current.title || last.idea !== current.idea) {
        lastProposedInputRef.current = current
        setProposedNodes([])
        void proposeSchema(density)
      }
    }
    prevPhaseRef.current = phase
  }, [phase]) // eslint-disable-line react-hooks/exhaustive-deps

  // Re-propose when density changes in schema phase
  const densityDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  function handleDensityChange(newDensity: number) {
    setDensity(newDensity)
    if (phase === 'schema') {
      if (densityDebounceRef.current) clearTimeout(densityDebounceRef.current)
      densityDebounceRef.current = setTimeout(() => {
        void proposeSchema(newDensity)
      }, 400)
    }
  }

  const confirmSource = useCallback(() => {
    if (source) setPhase('details')
  }, [source])

  // Cleanup async operations on unmount
  useEffect(() => {
    return () => {
      proposeAbortRef.current?.abort()
      if (densityDebounceRef.current) clearTimeout(densityDebounceRef.current)
    }
  }, [])

  // Reset stream phase when leaving schema phase
  useEffect(() => {
    if (phase !== 'schema') {
      setStreamPhase('idle')
    }
  }, [phase])

  // Backward from details: useInstantLayoutTransition suppresses the reverse morph
  const goBackToChoose = useCallback(() => {
    startInstant(() => {
      setPhase('choose')
      setSource(null)
      uploader.clearUploads()
      setDocumentId(null)
    })
  }, [startInstant, uploader])

  // Backward from schema: same card, just swap content
  const goBackToDetails = useCallback(() => {
    setPhase('details')
  }, [])

  // Error helper
  function failMsg(err: unknown, fallback: string): string {
    if (err instanceof ApiError) return err.body.detail
    if (err instanceof Error && err.message) return err.message
    return fallback
  }

  async function ensureSourceDocument(): Promise<string | undefined> {
    if (documentId) return documentId
    if (source !== 'crear') return undefined
    setWritingSource(true)
    try {
      const doc = await createSource.mutateAsync({ title: title.trim(), idea: idea.trim() })
      await waitForDocumentReady(doc.id)
      setDocumentId(doc.id)
      return doc.id
    } finally {
      setWritingSource(false)
    }
  }

  async function handleConfirmDetails() {
    setStartError(null)

    if (deliveryChoice === 'dynamic') {
      // Go to schema phase -- proposal fires automatically via useEffect
      setPhase('schema')
      return
    }

    // Static path: create course + generate
    try {
      const sourceId = await ensureSourceDocument()
      const course = await createCourse.mutateAsync({
        title: title.trim(),
        description: idea.trim() || undefined,
        source_document_id: sourceId,
      })
      setCourseId(course.id)

      const job = await generate.mutateAsync({
        courseId: course.id,
        source_document_id: sourceId,
        output_type: 'course_and_manual',
      })
      setJobId(job.job_id)
      setPhase('generating')
    } catch (err) {
      setStartError(failMsg(err, intl.formatMessage({ id: 'create.courseError' })))
    }
  }

  // Creation progress steps
  const [creatingStep, setCreatingStep] = useState(0)
  const creatingSteps = [
    intl.formatMessage({ id: 'create.creatingTitle' }, { title: title.trim() || intl.formatMessage({ id: 'create.title' }) }),
    intl.formatMessage({ id: 'create.savingNodes' }, { count: proposedNodes.length }),
    intl.formatMessage({ id: 'create.activating' }),
    intl.formatMessage({ id: 'create.preparingFirst' }),
  ]

  async function handleCreateFromSchema() {
    setStartError(null)

    for (let i = 0; i < proposedNodes.length; i++) {
      if (!proposedNodes[i].title.trim()) {
        setStartError(intl.formatMessage({ id: 'create.nodeNoTitle' }, { num: i + 1 }))
        return
      }
    }

    // Transition immediately — the user sees progress, not a dead button
    setCreatingStep(0)
    setPhase('creating')

    try {
      const sourceId = source === 'importar' ? documentId ?? undefined : undefined
      const course = await createCourse.mutateAsync({
        title: title.trim(),
        description: idea.trim() || undefined,
        source_document_id: sourceId,
      })
      setCourseId(course.id)

      // Step 2: save nodes
      setCreatingStep(1)
      const toNodePayload = (n: ProposedNode, i: number, prereqIds: string[] = []) => ({
        title: n.title.trim(),
        summary: n.summary.trim() || n.title.trim(),
        outcome: n.outcome?.trim() || null,
        criticality: n.criticality,
        position: i + 1,
        mastery_threshold: n.criticality === 'critical' ? 0.9 : n.criticality === 'recommended' ? 0.8 : 0.7,
        estimated_minutes: n.estimated_minutes,
        default_ui_format: n.default_ui_format,
        skill_id: null,
        seed_lesson_id: null,
        source_document_id: sourceId ?? null,
        source_headings: n.source_headings,
        prerequisite_node_ids: prereqIds,
        archived: false,
      })

      const created = await put<{ nodes: { id: string; position: number }[] }>(
        `/courses/${course.id}/schema`,
        { intent_density: density, nodes: proposedNodes.map((n, i) => toNodePayload(n, i)) },
      )

      const hasPrereqs = proposedNodes.some((n) => n.prerequisites.length > 0)
      if (hasPrereqs) {
        const idByPosition = new Map(created.nodes.map((n) => [n.position, n.id]))
        const withPrereqs = proposedNodes.map((n, i) => {
          const prereqIds = n.prerequisites
            .map((idx) => idByPosition.get(idx + 1))
            .filter((id): id is string => id !== undefined)
          return { ...toNodePayload(n, i, prereqIds), id: idByPosition.get(i + 1) }
        })
        await put(`/courses/${course.id}/schema`, {
          intent_density: density,
          nodes: withPrereqs,
        })
      }

      // Step 3: activate
      setCreatingStep(2)
      const schema = await get<{ nodes: { id: string }[] }>(`/courses/${course.id}/schema`)
      for (const node of schema.nodes) {
        await post(`/courses/${course.id}/schema/nodes/${node.id}/review`, {}).catch(() => {})
      }
      await post(`/courses/${course.id}/schema/validate`, {}).catch(() => {})
      await post(`/courses/${course.id}/publish`, {}).catch(() => {})

      // Step 4: pre-render first node (non-blocking — go to success after a few seconds)
      setCreatingStep(3)
      const firstNode = schema.nodes[0]
      if (firstNode) {
        post(`/nodes/${firstNode.id}/render`, { force: false }).catch(() => {})
        // Give it a short window, then move on regardless
        await new Promise(r => setTimeout(r, 2000))
      }

      setCreatedTitle(title.trim())
      setCreatedNodeCount(proposedNodes.length)
      setCreatedMinutes(totalMinutes)
      setPhase('created')
    } catch (err) {
      setStartError(failMsg(err, intl.formatMessage({ id: 'create.courseError' })))
      setPhase('schema') // go back to schema on error
    }
  }

  function handlePublish() {
    if (!courseId) return
    publish.mutate(courseId, { onSuccess: () => setPublished(true) })
  }

  function toggleAssign(id: string) {
    setAssignSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function finish() {
    if (!courseId) return
    if (assignSelected.size === 0) { navigate('/admin/contenido'); return }
    assign.mutate(
      { user_ids: Array.from(assignSelected), course_id: courseId, deadline: deadline || undefined },
      { onSuccess: () => navigate('/admin/contenido') },
    )
  }

  // Remap prerequisite indices when nodes are reordered
  const handleNodeReorder = useCallback((from: number, to: number) => {
    setProposedNodes((ns) => {
      const moved = arrayMove(ns, from, to)
      const remap = new Map<number, number>()
      if (from < to) {
        remap.set(from, to)
        for (let i = from + 1; i <= to; i++) remap.set(i, i - 1)
      } else {
        remap.set(from, to)
        for (let i = to; i < from; i++) remap.set(i, i + 1)
      }
      return moved.map((n) => ({
        ...n,
        prerequisites: n.prerequisites.map((idx) => remap.get(idx) ?? idx),
      }))
    })
  }, [])

  // Remap prerequisite indices when a node is deleted
  const handleNodeDelete = useCallback((deleted: number) => {
    setProposedNodes((ns) =>
      ns
        .filter((_, j) => j !== deleted)
        .map((n) => ({
          ...n,
          prerequisites: n.prerequisites
            .filter((idx) => idx !== deleted)
            .map((idx) => (idx > deleted ? idx - 1 : idx)),
        })),
    )
  }, [])

  const handleNodeChange = useCallback((i: number, patch: Partial<ProposedNode>) => {
    setProposedNodes((ns) => ns.map((n, j) => (j === i ? { ...n, ...patch } : n)))
  }, [])

  const handleNodeAdd = useCallback(() => {
    setProposedNodes((ns) => [
      ...ns,
      {
        _key: nodeKeyCounter.current++,
        title: '',
        summary: '',
        outcome: null,
        criticality: 'recommended',
        default_ui_format: 'explanation',
        estimated_minutes: 5,
        source_headings: [],
        prerequisites: [],
      },
    ])
  }, [])

  const busyStarting = writingSource || createCourse.isPending || generate.isPending
  const documentReady = source !== 'importar' || !!documentId
  const canConfirm = title.trim().length > 0 && documentReady && !busyStarting

  const confirmButtonLabel = writingSource
    ? intl.formatMessage({ id: 'create.writingSource' })
    : createCourse.isPending || generate.isPending
      ? intl.formatMessage({ id: 'create.creating' })
      : intl.formatMessage({ id: 'create.confirm' })

  // Stats for schema sidebar
  const totalMinutes = proposedNodes.reduce((s, n) => s + n.estimated_minutes, 0)
  const criticalCount = proposedNodes.filter((n) => n.criticality === 'critical').length

  // ── Render ────────────────────────────────────────────────

  // Post-creation phases
  if (phase === 'creating') {
    return (
      <div>
        {/* Breadcrumb */}
        <div className="mb-6 flex items-baseline gap-1.5 text-xl font-semibold">
          <span className="text-text-muted">Crear curso</span>
          <span className="text-text-muted">/</span>
          <span className="text-text-muted">{source === 'importar' ? 'Importar' : 'Crear'}</span>
          <span className="text-text-muted">/</span>
          <span className="text-text-muted">Esquema</span>
          <span className="text-text-muted">/</span>
          <span className="text-text">Creando</span>
        </div>

        <div className="flex flex-col items-center justify-center py-16">
          <div className="w-full max-w-sm space-y-4">
            {creatingSteps.map((label, i) => {
              const done = i < creatingStep
              const active = i === creatingStep
              return (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: duration.normal, ease: [...ease.base], delay: i * 0.06 }}
                  className="flex items-center gap-3"
                >
                  {done ? (
                    <motion.div
                      className="w-5 h-5 rounded-full bg-primary flex items-center justify-center"
                      initial={{ scale: 0.5, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={{ duration: duration.fast, ease: ease.bounce }}
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    </motion.div>
                  ) : active ? (
                    <div className="w-5 h-5 rounded-full border-2 border-primary flex items-center justify-center">
                      <span className="w-2 h-2 rounded-full bg-primary" />
                    </div>
                  ) : (
                    <div className="w-5 h-5 rounded-full border-2 border-border" />
                  )}
                  <span className={`text-sm ${active ? 'text-text font-medium' : done ? 'text-text-muted' : 'text-text-muted/50'}`}>
                    {label}
                  </span>
                  {active && <span className="typing-dots text-primary" aria-hidden="true"><span /><span /><span /></span>}
                </motion.div>
              )
            })}
          </div>
        </div>
      </div>
    )
  }

  if (phase === 'generating') {
    return (
      <div>
        <div className="flex items-center gap-3 mb-8">
          <h2 className="text-xl font-semibold text-text">{intl.formatMessage({ id: 'create.generatingTitle' })}</h2>
        </div>
        <GenerationProgress progress={effective} />
        {effective.step === 'failed' && (
          <div className="mt-6 text-center">
            <Button variant="secondary" onClick={() => { setPhase('details'); setJobId(null) }}>{intl.formatMessage({ id: 'create.retryGeneration' })}</Button>
          </div>
        )}
      </div>
    )
  }

  if (phase === 'created') {
    return (
      <div>
        {/* Breadcrumb */}
        <div className="mb-6 flex items-baseline gap-1.5 text-xl font-semibold">
          <span className="text-text-muted">{intl.formatMessage({ id: 'create.title' })}</span>
          <span className="text-text-muted">/</span>
          <span className="text-text-muted">{source === 'importar' ? intl.formatMessage({ id: 'create.breadcrumbImport' }) : intl.formatMessage({ id: 'create.breadcrumbCreate' })}</span>
          <span className="text-text-muted">/</span>
          <span className="text-text-muted">{intl.formatMessage({ id: 'create.breadcrumbSchema' })}</span>
          <span className="text-text-muted">/</span>
          <span className="text-text">{intl.formatMessage({ id: 'create.breadcrumbReady' })}</span>
        </div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1, transition: { duration: duration.normal, ease: ease.base } }}
          className="border border-border rounded-lg"
        >
          <div className="flex flex-col items-center text-center px-6 py-16">
            <motion.div
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1, transition: { duration: duration.normal, ease: ease.bounce } }}
            >
              <SuccessIcon />
            </motion.div>

            <motion.h2
              className="text-2xl font-semibold text-text mt-6"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0, transition: { duration: duration.normal, ease: ease.base, delay: 0.15 } }}
            >
              {intl.formatMessage({ id: 'create.ready' })}
            </motion.h2>

            <motion.p
              className="text-lg font-medium text-text-secondary mt-2"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0, transition: { duration: duration.normal, ease: ease.base, delay: 0.25 } }}
            >
              {createdTitle}
            </motion.p>

            <motion.p
              className="text-sm text-text-muted mt-1.5"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0, transition: { duration: duration.normal, ease: ease.base, delay: 0.35 } }}
            >
              {intl.formatMessage({ id: 'create.nodesMinutes' }, { count: createdNodeCount, minutes: createdMinutes })}
            </motion.p>

            <motion.div
              className="flex flex-col sm:flex-row items-center gap-3 mt-10"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0, transition: { duration: duration.normal, ease: ease.base, delay: 0.5 } }}
            >
              <Button
                variant="primary"
                disabled={testingCourse}
                onClick={async () => {
                  if (!courseId || !currentUser) return
                  setTestingCourse(true)
                  try {
                    await post('/enrollments', { user_ids: [currentUser.id], course_id: courseId }).catch(() => {})
                    // Go directly to the first node — no intermediate CourseView
                    try {
                      const nodesData = await get<{ nodes: { id: string; position: number }[] }>(`/courses/${courseId}/nodes`)
                      const first = [...nodesData.nodes].sort((a, b) => a.position - b.position)[0]
                      if (first) {
                        navigate(`/admin/probar-curso/${courseId}/nodo/${first.id}`)
                      } else {
                        navigate(`/admin/probar-curso/${courseId}`)
                      }
                    } catch {
                      navigate(`/admin/probar-curso/${courseId}`)
                    }
                  } catch {
                    setTestingCourse(false)
                  }
                }}
              >
                {testingCourse ? intl.formatMessage({ id: 'create.testing' }) : intl.formatMessage({ id: 'create.test' })}
              </Button>
              <Button variant="secondary" onClick={() => setPhase('assign')}>
                {intl.formatMessage({ id: 'create.assign' })}
              </Button>
              <Button variant="ghost" onClick={() => navigate('/admin/contenido')}>
                {intl.formatMessage({ id: 'create.backToContent' })}
              </Button>
            </motion.div>
          </div>
        </motion.div>
      </div>
    )
  }

  if (phase === 'review') {
    return (
      <div>
        <div className="flex items-center gap-3 mb-8">
          <h2 className="text-xl font-semibold text-text">{intl.formatMessage({ id: 'create.reviewTitle' })}</h2>
        </div>
        {courseId && <StepReview courseId={courseId} onPublish={handlePublish} publishing={publish.isPending} published={published} />}
        <div className="flex justify-end mt-8 pt-5 border-t border-border">
          <Button variant="primary" onClick={() => setPhase('assign')}>{intl.formatMessage({ id: 'create.next' })}</Button>
        </div>
      </div>
    )
  }

  if (phase === 'assign') {
    return (
      <div>
        {/* Breadcrumb */}
        <div className="mb-6 flex items-baseline gap-1.5 text-xl font-semibold">
          <span className="text-text-muted">{intl.formatMessage({ id: 'create.title' })}</span>
          <span className="text-text-muted">/</span>
          <span className="text-text-muted">{source === 'importar' ? intl.formatMessage({ id: 'create.breadcrumbImport' }) : intl.formatMessage({ id: 'create.breadcrumbCreate' })}</span>
          <span className="text-text-muted">/</span>
          <span className="text-text-muted">{intl.formatMessage({ id: 'create.breadcrumbSchema' })}</span>
          <span className="text-text-muted">/</span>
          <span className="text-text">{intl.formatMessage({ id: 'create.breadcrumbAssign' })}</span>
        </div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1, transition: { duration: duration.normal, ease: ease.base } }}
          className="border border-border p-6"
          style={{ borderRadius: 8 }}
        >
          <StepAssign selected={assignSelected} onToggle={toggleAssign} deadline={deadline} onDeadline={setDeadline} />
          {startError && <p className="text-sm text-danger mt-4">{startError}</p>}
          <div className="flex items-center justify-between mt-8 pt-5 border-t border-border">
            <Button variant="ghost" onClick={() => navigate('/admin/contenido')}>
              {intl.formatMessage({ id: 'create.skip' })}
            </Button>
            <div className="flex items-center gap-3">
              {courseId && (
                <Button
                  variant="secondary"
                  onClick={async () => {
                    if (!courseId || !currentUser) return
                    try {
                      // 1. Try to validate directly (fails if not reviewed)
                      await post(`/courses/${courseId}/schema/validate`, {}).catch(async () => {
                        // Review all nodes first, then validate
                        const schema = await get<{ nodes: { id: string }[] }>(`/courses/${courseId}/schema`)
                        for (const node of schema.nodes) {
                          await post(`/courses/${courseId}/schema/nodes/${node.id}/review`, {}).catch(() => {})
                        }
                        await post(`/courses/${courseId}/schema/validate`, {})
                      })
                      // 2. Enroll admin (ignore conflict if already enrolled)
                      await post('/enrollments', { user_ids: [currentUser.id], course_id: courseId }).catch(() => {})
                      // 3. Navigate directly to first node
                      try {
                        const nodesData = await get<{ nodes: { id: string; position: number }[] }>(`/courses/${courseId}/nodes`)
                        const first = [...nodesData.nodes].sort((a, b) => a.position - b.position)[0]
                        if (first) {
                          navigate(`/admin/probar-curso/${courseId}/nodo/${first.id}`)
                        } else {
                          navigate(`/admin/probar-curso/${courseId}`)
                        }
                      } catch {
                        navigate(`/admin/probar-curso/${courseId}`)
                      }
                    } catch {
                      setStartError(intl.formatMessage({ id: 'create.prepareError' }))
                    }
                  }}
                  disabled={assign.isPending}
                >
                  {intl.formatMessage({ id: 'create.test' })}
                </Button>
              )}
              <Button variant="primary" onClick={finish} disabled={assign.isPending}>
                {assign.isPending ? intl.formatMessage({ id: 'create.assigning' }) : assignSelected.size > 0 ? intl.formatMessage({ id: 'create.assignFinish' }) : intl.formatMessage({ id: 'create.finish' })}
              </Button>
            </div>
          </div>
        </motion.div>
      </div>
    )
  }

  // ── Choose + Details + Schema (morph flow) ────────────────

  const expanded = phase === 'details' || phase === 'schema'
  const activeCard = source

  return (
    <LayoutGroup>
      <div>
        {/* Header / Breadcrumb */}
        <div className="mb-6 shrink-0 flex items-baseline gap-1.5">
          <h2
            className={`text-xl font-semibold transition-colors duration-200 ${expanded ? 'text-text-muted cursor-pointer hover:text-text' : 'text-text'}`}
            onClick={expanded ? goBackToChoose : undefined}
            role={expanded ? 'button' : undefined}
          >
            {intl.formatMessage({ id: 'create.title' })}
          </h2>
          <AnimatePresence>
            {expanded && (
              <motion.span
                key="breadcrumb-source"
                className={`text-xl font-semibold transition-colors duration-200 ${
                  phase === 'schema' ? 'text-text-muted cursor-pointer hover:text-text' : 'text-text'
                }`}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0, transition: { duration: duration.normal, ease: ease.base, delay: 0.35 } }}
                exit={{ opacity: 0, x: -8, transition: { duration: duration.fast, ease: ease.snapOut } }}
                onClick={phase === 'schema' ? goBackToDetails : undefined}
                role={phase === 'schema' ? 'button' : undefined}
              >
                / {source === 'importar' ? intl.formatMessage({ id: 'create.breadcrumbImport' }) : intl.formatMessage({ id: 'create.breadcrumbCreate' })}
              </motion.span>
            )}
          </AnimatePresence>
          <AnimatePresence>
            {phase === 'schema' && (
              <motion.span
                key="breadcrumb-schema"
                className="text-xl font-semibold text-text"
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0, transition: { duration: duration.normal, ease: ease.base, delay: 0.35 } }}
                exit={{ opacity: 0, x: -8, transition: { duration: duration.fast, ease: ease.snapOut } }}
              >
                / {intl.formatMessage({ id: 'create.breadcrumbSchema' })}
              </motion.span>
            )}
          </AnimatePresence>
        </div>

        {/* Cards -- conditional rendering so layoutId connects forward morphs */}
        <div className={expanded ? '' : 'grid grid-cols-1 sm:grid-cols-2 gap-4'}>

          {/* Card: Importar curso */}
          {(activeCard === 'importar' || !expanded) && (
            <motion.div
              layoutId="source-card-importar"
              transition={morphTransition.layout}
              style={{ borderRadius: 8 }}
              className={`border p-6 ${
                expanded
                  ? 'border-primary bg-bg'
                  : source === 'importar'
                    ? 'border-primary bg-primary-subtle cursor-pointer'
                    : 'border-border hover:border-primary cursor-pointer'
              }`}
              onClick={() => { if (!expanded) setSource(source === 'importar' ? null : 'importar') }}
            >
              {!expanded ? (
                <motion.div key="import-col" {...contentReveal}>
                  <div className="flex flex-col items-center justify-center text-center px-4 py-8">
                    <div className="text-text-muted mb-4"><FileIcon /></div>
                    <p className="text-sm font-medium text-text">{intl.formatMessage({ id: 'create.importCard' })}</p>
                    <p className="text-xs text-text-muted mt-1.5">{intl.formatMessage({ id: 'create.importCardDesc' })}</p>
                  </div>
                </motion.div>
              ) : (
                <AnimatePresence mode="wait">
                  {phase === 'details' ? (
                    <motion.div key="import-details" {...innerFadeIn} {...innerFadeOut}>
                      <div className="flex items-center gap-3 mb-6">
                        <div className="text-primary"><FileIcon /></div>
                        <div>
                          <p className="text-sm font-medium text-text">{intl.formatMessage({ id: 'create.importCardExpanded' })}</p>
                          <p className="text-xs text-text-muted">{intl.formatMessage({ id: 'create.importCardExpandedDesc' })}</p>
                        </div>
                      </div>
                      <div className="space-y-5">
                        <FileUploadZone
                          accept=".pdf,.docx,.md,.txt"
                          maxSizeMB={20}
                          onFilesSelected={(files) => uploader.uploadFile(files[0]).catch(() => {})}
                        />
                        {uploader.uploads.length > 0 && (
                          <div className="space-y-2">
                            {uploader.uploads.map((u) => (
                              <UploadedFileRow
                                key={u.id}
                                upload={u}
                                onRemove={() => { uploader.removeUpload(u.id); if (u.documentId === documentId) setDocumentId(null) }}
                              />
                            ))}
                          </div>
                        )}
                        <Input label={intl.formatMessage({ id: 'create.courseNameLabel' })} placeholder={intl.formatMessage({ id: 'create.courseNamePlaceholder' })} value={title} onChange={(e) => setTitle(e.target.value)} />
                        <DeliverySelector value={deliveryChoice} onChange={setDeliveryChoice} />
                        {startError && <p className="text-sm text-danger">{startError}</p>}
                        <div className="pt-4">
                          <Button variant="primary" className="w-full" onClick={() => void handleConfirmDetails()} disabled={!canConfirm}>
                            {confirmButtonLabel}
                          </Button>
                        </div>
                      </div>
                    </motion.div>
                  ) : (
                    <motion.div key="import-schema" {...innerFadeIn} {...innerFadeOut}>
                      <SchemaContent
                        proposing={proposing}
                        proposeError={proposeError}
                        nodes={proposedNodes}
                        density={density}
                        onDensityChange={handleDensityChange}
                        totalMinutes={totalMinutes}
                        criticalCount={criticalCount}
                        onNodeChange={handleNodeChange}
                        onNodeDelete={handleNodeDelete}
                        onNodeAdd={handleNodeAdd}
                        onNodeReorder={handleNodeReorder}
                        onCreateCourse={() => void handleCreateFromSchema()}
                        creating={createCourse.isPending}
                        startError={startError}
                        enrichedNodes={enrichedNodes}
                        streamPhase={streamPhase}
                      />
                    </motion.div>
                  )}
                </AnimatePresence>
              )}
            </motion.div>
          )}

          {/* Card: Crear curso */}
          {(activeCard === 'crear' || !expanded) && (
            <motion.div
              layoutId="source-card-crear"
              transition={morphTransition.layout}
              style={{ borderRadius: 8 }}
              className={`border p-6 ${
                expanded
                  ? 'border-primary bg-bg'
                  : source === 'crear'
                    ? 'border-primary bg-primary-subtle cursor-pointer'
                    : 'border-border hover:border-primary cursor-pointer'
              }`}
              onClick={() => { if (!expanded) setSource(source === 'crear' ? null : 'crear') }}
            >
              {!expanded ? (
                <motion.div key="crear-col" {...contentReveal}>
                  <div className="flex flex-col items-center justify-center text-center px-4 py-8">
                    <div className="text-text-muted mb-4"><EditIcon /></div>
                    <p className="text-sm font-medium text-text">{intl.formatMessage({ id: 'create.createCard' })}</p>
                    <p className="text-xs text-text-muted mt-1.5">{intl.formatMessage({ id: 'create.createCardDesc' })}</p>
                  </div>
                </motion.div>
              ) : (
                <AnimatePresence mode="wait">
                  {phase === 'details' ? (
                    <motion.div key="crear-details" {...innerFadeIn} {...innerFadeOut}>
                      <div className="flex items-center gap-3 mb-6">
                        <div className="text-primary"><EditIcon /></div>
                        <div>
                          <p className="text-sm font-medium text-text">{intl.formatMessage({ id: 'create.createCardExpanded' })}</p>
                          <p className="text-xs text-text-muted">{intl.formatMessage({ id: 'create.createCardExpandedDesc' })}</p>
                        </div>
                      </div>
                      <div className="space-y-5">
                        <Input label={intl.formatMessage({ id: 'create.courseNameLabel' })} placeholder={intl.formatMessage({ id: 'create.courseNamePlaceholder' })} value={title} onChange={(e) => setTitle(e.target.value)} />
                        <Textarea
                          label={intl.formatMessage({ id: 'create.ideaLabel' })}
                          placeholder={intl.formatMessage({ id: 'create.ideaPlaceholder' })}
                          hint={intl.formatMessage({ id: 'create.ideaHint' })}
                          value={idea}
                          onChange={(e) => setIdea(e.target.value)}
                        />

                        {/* Reference documents (optional) */}
                        <div>
                          <label className="block text-sm font-medium text-text mb-2">{intl.formatMessage({ id: 'create.refMaterialLabel' })}</label>
                          <p className="text-xs text-text-muted mb-3">{intl.formatMessage({ id: 'create.refMaterialDesc' })}</p>
                          <FileUploadZone
                            accept=".pdf,.docx,.md,.txt"
                            maxSizeMB={20}
                            onFilesSelected={(files) => uploader.uploadFile(files[0]).catch(() => {})}
                          />
                          {uploader.uploads.length > 0 && (
                            <div className="space-y-2 mt-3">
                              {uploader.uploads.map((u) => (
                                <UploadedFileRow
                                  key={u.id}
                                  upload={u}
                                  onRemove={() => { uploader.removeUpload(u.id); if (u.documentId === documentId) setDocumentId(null) }}
                                />
                              ))}
                            </div>
                          )}
                        </div>

                        <DeliverySelector value={deliveryChoice} onChange={setDeliveryChoice} />
                        {startError && <p className="text-sm text-danger">{startError}</p>}
                        <div className="pt-4">
                          <Button variant="primary" className="w-full" onClick={() => void handleConfirmDetails()} disabled={!canConfirm}>
                            {confirmButtonLabel}
                          </Button>
                        </div>
                      </div>
                    </motion.div>
                  ) : (
                    <motion.div key="crear-schema" {...innerFadeIn} {...innerFadeOut}>
                      <SchemaContent
                        proposing={proposing}
                        proposeError={proposeError}
                        nodes={proposedNodes}
                        density={density}
                        onDensityChange={handleDensityChange}
                        totalMinutes={totalMinutes}
                        criticalCount={criticalCount}
                        onNodeChange={handleNodeChange}
                        onNodeDelete={handleNodeDelete}
                        onNodeAdd={handleNodeAdd}
                        onNodeReorder={handleNodeReorder}
                        onCreateCourse={() => void handleCreateFromSchema()}
                        creating={createCourse.isPending}
                        startError={startError}
                        enrichedNodes={enrichedNodes}
                        streamPhase={streamPhase}
                      />
                    </motion.div>
                  )}
                </AnimatePresence>
              )}
            </motion.div>
          )}
        </div>

        {/* Confirm button when a source is selected but not expanded */}
        <AnimatePresence>
          {source && !expanded && (
            <motion.div
              className="flex justify-center mt-6"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0, transition: { duration: duration.normal, ease: ease.base } }}
              exit={{ opacity: 0, y: 8, transition: { duration: duration.fast, ease: ease.snapOut } }}
            >
              <Button variant="primary" onClick={confirmSource}>
                {intl.formatMessage({ id: 'create.continue' })}
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </LayoutGroup>
  )
}
