import { useEffect, useState, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence, LayoutGroup, useInstantLayoutTransition } from 'framer-motion'
import { DndContext, closestCenter, PointerSensor, KeyboardSensor, useSensor, useSensors } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy, useSortable, arrayMove } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { ease, duration } from '../../lib/motion'
import { Button, Input, Textarea, Badge, EmptyState, FileUploadZone, ProgressBar } from '../../components/ui'
import { ShimmerSkeleton } from '../../components/ui/ShimmerSkeleton'
import { GenerationProgress } from '../../components/generation/GenerationProgress'
import {
  useUploadDocument,
  useProcessDocument,
  useCreateSourceFromIdea,
  waitForDocumentReady,
} from '../../api/documents'
import { useCreateCourse, useGenerateContent, usePublishCourse, useCourse, useUpdateLesson, useUpdateExercise } from '../../api/courses'
import { useGenerationProgress, useGenerationJobStatus, jobToProgress } from '../../api/generation'
import { useUsers } from '../../api/users'
import { useAssignCourse } from '../../api/enrollments'
import { ApiError, post, put } from '../../api/client'
import type { GenerationProgress as GenProgress, User, Lesson, Exercise } from '../../types'

type SourceType = 'importar' | 'crear' | null
type DeliveryChoice = 'dynamic' | 'static'
type Phase = 'choose' | 'details' | 'schema' | 'generating' | 'review' | 'assign'

interface ProposedNode {
  _key: number
  title: string
  summary: string
  outcome: string | null
  criticality: string
  default_ui_format: string
  estimated_minutes: number
  source_headings: string[]
  prerequisites: number[]
}

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
      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
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
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={`transition-transform ${open ? 'rotate-90' : ''}`}>
      <polyline points="9 18 15 12 9 6" />
    </svg>
  )
}


function InfoTooltip({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="relative inline-flex">
      <button
        type="button"
        className="text-text-muted hover:text-primary p-0 ml-1"
        onClick={() => setOpen(!open)}
        onBlur={() => setOpen(false)}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" /><line x1="12" y1="16" x2="12" y2="12" /><line x1="12" y1="8" x2="12.01" y2="8" />
        </svg>
      </button>
      {open && (
        <span className="absolute left-0 top-6 z-10 w-56 bg-text text-bg text-xs rounded-md px-3 py-2 shadow-md leading-relaxed">
          {text}
        </span>
      )}
    </span>
  )
}

function PlusIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

// ── Inline editable lesson (unchanged logic) ─────────────────

function EditableLesson({ lesson }: { lesson: Lesson }) {
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
            <input className="flex-1 min-w-0 text-sm border border-border rounded px-2 py-1 bg-bg text-text focus:outline-none focus:border-primary" value={titleDraft} onChange={(e) => setTitleDraft(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') saveTitle(); if (e.key === 'Escape') cancelTitle() }} autoFocus />
            <button type="button" onClick={saveTitle} className="text-accent hover:text-accent/80 p-0.5" title="Guardar"><SaveIcon /></button>
            <button type="button" onClick={cancelTitle} className="text-text-muted hover:text-text p-0.5" title="Cancelar"><XIcon /></button>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 flex-1 min-w-0 group">
            <span className="text-text-secondary truncate min-w-0">{lesson.title}</span>
            <button type="button" onClick={() => { setTitleDraft(lesson.title); setEditingTitle(true) }} className="text-text-muted hover:text-primary opacity-0 group-hover:opacity-100 transition-opacity p-0.5 shrink-0" title="Editar titulo"><PencilIcon /></button>
          </div>
        )}
      </div>
      {expanded && (
        <div className="mt-3 ml-6">
          <div className="mb-2">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-text-muted uppercase tracking-wide">Contenido</span>
              {!editingContent && <button type="button" onClick={() => { setContentDraft(lesson.content); setEditingContent(true) }} className="text-text-muted hover:text-primary p-0.5" title="Editar contenido"><PencilIcon /></button>}
            </div>
            {editingContent ? (
              <div>
                <textarea className="w-full text-sm border border-border rounded px-3 py-2 bg-bg text-text focus:outline-none focus:border-primary font-mono min-h-[120px] resize-y" value={contentDraft} onChange={(e) => setContentDraft(e.target.value)} rows={8} />
                <div className="flex items-center gap-2 mt-1.5">
                  <Button size="sm" variant="primary" onClick={saveContent} disabled={updateLesson.isPending}>{updateLesson.isPending ? 'Guardando...' : 'Guardar'}</Button>
                  <Button size="sm" variant="secondary" onClick={cancelContent}>Cancelar</Button>
                </div>
              </div>
            ) : (
              <pre className="text-xs text-text-secondary bg-bg-subtle rounded p-2 whitespace-pre-wrap max-h-40 overflow-y-auto">{lesson.content.slice(0, 500)}{lesson.content.length > 500 ? '...' : ''}</pre>
            )}
          </div>
          {lesson.exercises.length > 0 && (
            <div>
              <span className="text-xs font-medium text-text-muted uppercase tracking-wide">Ejercicios ({lesson.exercises.length})</span>
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
            {(exercise.content as unknown as Record<string, unknown>).question as string
              ?? (exercise.content as unknown as Record<string, unknown>).statement as string
              ?? (exercise.content as unknown as Record<string, unknown>).instruction as string
              ?? (exercise.content as unknown as Record<string, unknown>).context as string
              ?? ''}
          </span>
        </div>
        {!editing && <button type="button" onClick={() => { setDraft(JSON.stringify(exercise.content, null, 2)); setEditing(true) }} className="text-text-muted hover:text-primary p-0.5 shrink-0" title="Editar ejercicio"><PencilIcon /></button>}
      </div>
      {editing && (
        <div className="mt-2">
          <textarea className="w-full text-xs border border-border rounded px-3 py-2 bg-bg text-text focus:outline-none focus:border-primary font-mono min-h-[100px] resize-y" value={draft} onChange={(e) => setDraft(e.target.value)} rows={6} />
          <div className="flex items-center gap-2 mt-1.5">
            <Button size="sm" variant="primary" onClick={save} disabled={updateExercise.isPending}>{updateExercise.isPending ? 'Guardando...' : 'Guardar'}</Button>
            <Button size="sm" variant="secondary" onClick={cancel}>Cancelar</Button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Review step ──────────────────────────────────────────────

function StepReview({ courseId, onPublish, publishing, published }: { courseId: string; onPublish: () => void; publishing: boolean; published: boolean }) {
  const { data: course, isLoading } = useCourse(courseId)
  if (isLoading) return <p className="text-sm text-text-secondary">Cargando...</p>
  if (!course) return <EmptyState title="No se pudo cargar el curso generado" />
  const totalLessons = course.modules.reduce((acc, m) => acc + m.lessons.length, 0)
  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-text-secondary">{course.modules.length} modulos · {totalLessons} lecciones</p>
        <Button size="sm" variant="accent" onClick={onPublish} disabled={publishing || published}>
          {published ? 'Publicado' : publishing ? 'Publicando...' : 'Publicar'}
        </Button>
      </div>
      <div className="mt-6 space-y-3">
        {course.modules.map((mod, i) => (
          <div key={mod.id} className="border border-border rounded-lg p-5">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-base font-medium text-text truncate min-w-0">Modulo {i + 1}: {mod.title}</h3>
              <Badge variant="accent" badgeStyle="plain">{mod.lessons.length} lecciones</Badge>
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

// ── Assign step ──────────────────────────────────────────────

function StepAssign({ selected, onToggle, deadline, onDeadline }: {
  selected: Set<string>; onToggle: (id: string) => void; deadline: string; onDeadline: (v: string) => void
}) {
  const { data, isLoading } = useUsers({ role: 'employee' })
  const employees: User[] = data?.items ?? []
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      <div>
        <label className="block text-sm font-medium text-text mb-2">Empleados</label>
        <div className="border border-border rounded-lg max-h-64 overflow-y-auto">
          {isLoading ? <p className="text-sm text-text-muted p-4">Cargando...</p>
            : employees.length === 0 ? <p className="text-sm text-text-muted p-4">No hay empleados.</p>
            : employees.map((emp) => (
              <label key={emp.id} className="flex items-center gap-3 px-4 py-2.5 border-b border-border last:border-b-0 hover:bg-bg-subtle cursor-pointer transition-colors">
                <input type="checkbox" checked={selected.has(emp.id)} onChange={() => onToggle(emp.id)} className="accent-primary" />
                <div className="min-w-0">
                  <p className="text-sm text-text truncate">{emp.full_name}</p>
                  <p className="text-xs text-text-muted truncate">{emp.email}</p>
                </div>
              </label>
            ))}
        </div>
        <p className="text-xs text-text-muted mt-1.5">{selected.size} seleccionados</p>
      </div>
      <div>
        <Input label="Fecha limite (opcional)" type="date" value={deadline} onChange={(e) => onDeadline(e.target.value)} />
      </div>
    </div>
  )
}

// ── Transitions ──────────────────────────────────────────────

const morphTransition = {
  layout: { type: 'spring' as const, stiffness: 200, damping: 28 },
}

// Content inside cards — opacity only, no blur.
const contentReveal = {
  initial: { opacity: 0 },
  animate: {
    opacity: 1,
    transition: { duration: duration.normal, ease: ease.base, delay: 0.35 },
  },
}

// Inner content swap (details <-> schema) — opacity only, no blur.
const innerFadeOut = {
  exit: { opacity: 0, transition: { duration: duration.fast, ease: ease.base } },
}
const innerFadeIn = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: duration.normal, ease: ease.base } },
}


// ── Main component ───────────────────────────────────────────

export function CreateCourse() {
  const navigate = useNavigate()

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

  // Schema proposal state (direct post, no hooks)
  const [proposedNodes, setProposedNodes] = useState<ProposedNode[]>([])
  const [proposing, setProposing] = useState(false)
  const [proposeError, setProposeError] = useState<string | null>(null)
  const [density, setDensity] = useState(3)
  const proposeAbortRef = useRef<AbortController | null>(null)
  const nodeKeyCounter = useRef(0)
  const assignKeys = useCallback((nodes: Omit<ProposedNode, '_key'>[]): ProposedNode[] =>
    nodes.map(n => ({ ...n, _key: '_key' in n ? (n as ProposedNode)._key : nodeKeyCounter.current++ })),
  [])

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

  // Schema proposal: call POST /api/v1/ai/schema-propose directly
  const proposeSchema = useCallback(async (d: number) => {
    proposeAbortRef.current?.abort()
    const abort = new AbortController()
    proposeAbortRef.current = abort

    setProposing(true)
    setProposeError(null)

    try {
      const result = await post<{ nodes: Omit<ProposedNode, '_key'>[] }>('/ai/schema-propose', {
        title: title.trim(),
        description: idea.trim() || undefined,
        intent_density: d,
      })
      if (!abort.signal.aborted) {
        setProposedNodes(assignKeys(result.nodes))
        setProposing(false)
      }
    } catch (err) {
      if (!abort.signal.aborted) {
        setProposing(false)
        if (err instanceof ApiError) {
          setProposeError(err.body.detail)
        } else if (err instanceof Error) {
          setProposeError(err.message)
        } else {
          setProposeError('No se pudo disenar el esquema')
        }
      }
    }
  }, [title, idea, assignKeys])

  // Auto-propose when entering schema from details — re-propose if title/idea changed
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

  // Backward from details: useInstantLayoutTransition suppresses the reverse morph
  const goBackToChoose = useCallback(() => {
    startInstant(() => {
      setPhase('choose')
      setSource(null)
    })
  }, [startInstant])

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
      // Go to schema phase — proposal fires automatically via useEffect
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
      setStartError(failMsg(err, 'No se pudo crear el curso'))
    }
  }

  async function handleCreateFromSchema() {
    setStartError(null)
    try {
      const sourceId = source === 'importar' ? documentId ?? undefined : undefined
      const course = await createCourse.mutateAsync({
        title: title.trim(),
        description: idea.trim() || undefined,
        source_document_id: sourceId,
      })
      setCourseId(course.id)

      // Save the proposed nodes as the course schema (two-step: create nodes, then wire prerequisites)
      const toNodePayload = (n: ProposedNode, i: number, prereqIds: string[] = []) => ({
        title: n.title,
        summary: n.summary,
        outcome: n.outcome,
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

      // Step 1: create nodes without prerequisites
      const created = await put<{ nodes: { id: string; position: number }[] }>(
        `/courses/${course.id}/schema`,
        { intent_density: density, nodes: proposedNodes.map((n, i) => toNodePayload(n, i)) },
      )

      // Step 2: if any node has prerequisites, re-PUT with the real UUIDs
      const hasPrereqs = proposedNodes.some(n => n.prerequisites.length > 0)
      if (hasPrereqs) {
        const idByPosition = new Map(created.nodes.map(n => [n.position, n.id]))
        const withPrereqs = proposedNodes.map((n, i) => {
          const prereqIds = n.prerequisites
            .map(idx => idByPosition.get(idx + 1))
            .filter((id): id is string => id !== undefined)
          return { ...toNodePayload(n, i, prereqIds), id: idByPosition.get(i + 1) }
        })
        await put(`/courses/${course.id}/schema`, {
          intent_density: density,
          nodes: withPrereqs,
        })
      }

      setPhase('assign')
    } catch (err) {
      setStartError(failMsg(err, 'No se pudo crear el curso'))
    }
  }

  function handlePublish() {
    if (!courseId) return
    publish.mutate(courseId, { onSuccess: () => setPublished(true) })
  }

  function toggleAssign(id: string) {
    setAssignSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
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
    setProposedNodes(ns => {
      const moved = arrayMove(ns, from, to)
      // Build old-index -> new-index mapping
      const remap = new Map<number, number>()
      if (from < to) {
        remap.set(from, to)
        for (let i = from + 1; i <= to; i++) remap.set(i, i - 1)
      } else {
        remap.set(from, to)
        for (let i = to; i < from; i++) remap.set(i, i + 1)
      }
      return moved.map(n => ({
        ...n,
        prerequisites: n.prerequisites.map(idx => remap.get(idx) ?? idx),
      }))
    })
  }, [])

  // Remap prerequisite indices when a node is deleted
  const handleNodeDelete = useCallback((deleted: number) => {
    setProposedNodes(ns =>
      ns
        .filter((_, j) => j !== deleted)
        .map(n => ({
          ...n,
          prerequisites: n.prerequisites
            .filter(idx => idx !== deleted)
            .map(idx => (idx > deleted ? idx - 1 : idx)),
        })),
    )
  }, [])

  const busyStarting = writingSource || createCourse.isPending || generate.isPending
  const documentReady = source !== 'importar' || !!documentId
  const canConfirm = title.trim().length > 0 && documentReady && !busyStarting

  const confirmButtonLabel = writingSource
    ? 'Escribiendo documento fuente...'
    : createCourse.isPending || generate.isPending
      ? 'Creando...'
      : 'Confirmar'

  // ── Render ─────────────────────────────────────────────────

  // Post-creation phases
  if (phase === 'generating') {
    return (
      <div>
        <div className="flex items-center gap-3 mb-8">
          <h2 className="text-xl font-semibold text-text">Generando curso</h2>
        </div>
        <GenerationProgress progress={effective} />
        {effective.step === 'failed' && (
          <div className="mt-6 text-center">
            <Button variant="secondary" onClick={() => { setPhase('details'); setJobId(null) }}>Volver a intentar</Button>
          </div>
        )}
      </div>
    )
  }

  if (phase === 'review') {
    return (
      <div>
        <div className="flex items-center gap-3 mb-8">
          <h2 className="text-xl font-semibold text-text">Revisar curso</h2>
        </div>
        {courseId && <StepReview courseId={courseId} onPublish={handlePublish} publishing={publish.isPending} published={published} />}
        <div className="flex justify-end mt-8 pt-5 border-t border-border">
          <Button variant="primary" onClick={() => setPhase('assign')}>Siguiente</Button>
        </div>
      </div>
    )
  }

  if (phase === 'assign') {
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
          <span className="text-text">Asignar</span>
        </div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1, transition: { duration: duration.normal } }}
          className="border border-border p-6"
          style={{ borderRadius: 8 }}
        >
          <StepAssign selected={assignSelected} onToggle={toggleAssign} deadline={deadline} onDeadline={setDeadline} />
          <div className="flex items-center justify-between mt-8 pt-5 border-t border-border">
            <Button variant="ghost" onClick={() => navigate('/admin/contenido')}>
              Saltar
            </Button>
            <Button variant="primary" onClick={finish} disabled={assign.isPending}>
              {assign.isPending ? 'Asignando...' : assignSelected.size > 0 ? 'Asignar y finalizar' : 'Finalizar'}
            </Button>
          </div>
        </motion.div>
      </div>
    )
  }

  // ── Choose + Details + Schema (morph flow) ────────────────

  const expanded = phase === 'details' || phase === 'schema'
  const activeCard = source // which card is layoutId-morphed

  // Stats for schema sidebar
  const totalMinutes = proposedNodes.reduce((s, n) => s + n.estimated_minutes, 0)
  const criticalCount = proposedNodes.filter(n => n.criticality === 'critical').length

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
            Crear curso
          </h2>
          <AnimatePresence>
            {expanded && (
              <motion.span
                key="breadcrumb-source"
                className={`text-xl font-semibold transition-colors duration-200 ${phase === 'schema' ? 'text-text-muted cursor-pointer hover:text-text' : 'text-text'}`}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0, transition: { duration: duration.normal, ease: ease.base } }}
                exit={{ opacity: 0, x: -8, transition: { duration: duration.fast, ease: ease.snapOut } }}
                onClick={phase === 'schema' ? goBackToDetails : undefined}
                role={phase === 'schema' ? 'button' : undefined}
              >
                / {source === 'importar' ? 'Importar' : 'Crear'}
              </motion.span>
            )}
          </AnimatePresence>
          <AnimatePresence>
            {phase === 'schema' && (
              <motion.span
                key="breadcrumb-schema"
                className="text-xl font-semibold text-text"
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0, transition: { duration: duration.normal, ease: ease.base } }}
                exit={{ opacity: 0, x: -8, transition: { duration: duration.fast, ease: ease.snapOut } }}
              >
                / Esquema
              </motion.span>
            )}
          </AnimatePresence>
        </div>

        {/* Cards — conditional rendering so layoutId connects forward morphs */}
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
                    <p className="text-sm font-medium text-text">Importar curso</p>
                    <p className="text-xs text-text-muted mt-1.5">Sube los materiales que ya tienes</p>
                  </div>
                </motion.div>
              ) : (
                <AnimatePresence mode="wait">
                  {phase === 'details' ? (
                    <motion.div key="import-details" {...innerFadeIn} {...innerFadeOut}>
                      <div className="flex items-center gap-3 mb-6">
                        <div className="text-primary"><FileIcon /></div>
                        <div>
                          <p className="text-sm font-medium text-text">Importar curso existente</p>
                          <p className="text-xs text-text-muted">Sube tus materiales y la plataforma los estructura</p>
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
                            {uploader.uploads.map((u, i) => (
                              <div key={i} className="flex items-center gap-3 border border-border rounded-lg px-3 py-2.5">
                                <div className="shrink-0 w-8 h-8 rounded bg-bg-muted flex items-center justify-center">
                                  <FileIcon />
                                </div>
                                <div className="flex-1 min-w-0">
                                  <p className="text-sm text-text truncate">{u.file.name}</p>
                                  <p className="text-xs text-text-muted">
                                    {(u.file.size / 1024).toFixed(0)} KB
                                    {u.status === 'uploading' && ` · Subiendo...`}
                                    {u.status === 'processing' && ` · Procesando...`}
                                    {u.status === 'ready' && ` · Listo`}
                                    {u.status === 'error' && ` · Error`}
                                  </p>
                                  {u.status === 'uploading' && <ProgressBar value={u.progress} size="sm" className="mt-1.5" />}
                                </div>
                                {(u.status === 'ready' || u.status === 'processing') && (
                                  <span className="text-accent shrink-0"><CheckIcon /></span>
                                )}
                                {u.status === 'error' && (
                                  <span className="text-danger text-xs shrink-0">{u.error}</span>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                        <Input label="Nombre del curso" placeholder="Ej: Seguridad Alimentaria" value={title} onChange={(e) => setTitle(e.target.value)} />
                        <DeliverySelector value={deliveryChoice} onChange={setDeliveryChoice} />
                        {startError && <p className="text-sm text-danger">{startError}</p>}
                        <div className="pt-4">
                          <Button variant="primary" className="w-full" onClick={() => void handleConfirmDetails()} disabled={!canConfirm}>{confirmButtonLabel}</Button>
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
                        onNodeChange={(i, patch) => setProposedNodes(ns => ns.map((n, j) => j === i ? { ...n, ...patch } : n))}
                        onNodeDelete={handleNodeDelete}
                        onNodeAdd={() => setProposedNodes(ns => [...ns, { _key: nodeKeyCounter.current++, title: '', summary: '', outcome: null, criticality: 'recommended', default_ui_format: 'explanation', estimated_minutes: 5, source_headings: [], prerequisites: [] }])}
                        onNodeReorder={handleNodeReorder}
                        onCreateCourse={() => void handleCreateFromSchema()}
                        creating={createCourse.isPending}
                        startError={startError}
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
                    <p className="text-sm font-medium text-text">Crear curso</p>
                    <p className="text-xs text-text-muted mt-1.5">Describe el tema y la IA construye el curso</p>
                  </div>
                </motion.div>
              ) : (
                <AnimatePresence mode="wait">
                  {phase === 'details' ? (
                    <motion.div key="crear-details" {...innerFadeIn} {...innerFadeOut}>
                      <div className="flex items-center gap-3 mb-6">
                        <div className="text-primary"><EditIcon /></div>
                        <div>
                          <p className="text-sm font-medium text-text">Crear curso nuevo</p>
                          <p className="text-xs text-text-muted">Describe el tema y la IA construye el contenido</p>
                        </div>
                      </div>
                      <div className="space-y-5">
                        <Input label="Nombre del curso" placeholder="Ej: Seguridad Alimentaria" value={title} onChange={(e) => setTitle(e.target.value)} />
                        <Textarea
                          label="Que quieres que cubra (opcional)"
                          placeholder="Ej: como funciona una sinapsis, los neurotransmisores principales y la plasticidad. Nivel introductorio."
                          hint="Cuanto mas detalle, mejor sera el curso generado."
                          value={idea}
                          onChange={(e) => setIdea(e.target.value)}
                        />
                        <DeliverySelector value={deliveryChoice} onChange={setDeliveryChoice} />
                        {startError && <p className="text-sm text-danger">{startError}</p>}
                        <div className="pt-4">
                          <Button variant="primary" className="w-full" onClick={() => void handleConfirmDetails()} disabled={!canConfirm}>{confirmButtonLabel}</Button>
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
                        onNodeChange={(i, patch) => setProposedNodes(ns => ns.map((n, j) => j === i ? { ...n, ...patch } : n))}
                        onNodeDelete={handleNodeDelete}
                        onNodeAdd={() => setProposedNodes(ns => [...ns, { _key: nodeKeyCounter.current++, title: '', summary: '', outcome: null, criticality: 'recommended', default_ui_format: 'explanation', estimated_minutes: 5, source_headings: [], prerequisites: [] }])}
                        onNodeReorder={handleNodeReorder}
                        onCreateCourse={() => void handleCreateFromSchema()}
                        creating={createCourse.isPending}
                        startError={startError}
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
                Continuar
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </LayoutGroup>
  )
}

// ── Schema content (inside the expanded card) ────────────────

const CRITICALITY_OPTIONS: { value: string; label: string }[] = [
  { value: 'critical', label: 'Imprescindible' },
  { value: 'recommended', label: 'Recomendado' },
  { value: 'contextual', label: 'Contexto' },
]

const FORMAT_OPTIONS: { value: string; label: string }[] = [
  { value: 'explanation', label: 'Explicacion' },
  { value: 'exercise', label: 'Ejercicio' },
  { value: 'chart', label: 'Grafico' },
  { value: 'mixed', label: 'Mixto' },
]

function TreeNodeSkeleton({ opacity }: { opacity: number }) {
  return (
    <div className="flex items-center gap-0 px-2 py-1.5" style={{ opacity }}>
      <div className="w-5 shrink-0" />
      <ShimmerSkeleton className="w-5 h-5 rounded-full shrink-0" />
      <ShimmerSkeleton className="h-3.5 ml-2 rounded w-3/5" />
      <ShimmerSkeleton className="h-3 w-10 ml-auto rounded" />
    </div>
  )
}

// ── Sortable tree node ──────────────────────────────────────

function SortableTreeNode({ id, index, node, nodes, expanded, onToggle, onChange, onDelete }: {
  id: string
  index: number
  node: ProposedNode
  nodes: ProposedNode[]
  expanded: boolean
  onToggle: () => void
  onChange: (patch: Partial<ProposedNode>) => void
  onDelete: () => void
}) {
  const { attributes, listeners, setNodeRef, transform, transition: dndTransition, isDragging } = useSortable({ id })
  const style = {
    transform: CSS.Transform.toString(transform),
    transition: dndTransition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 10 : undefined,
  }

  const critClass = node.criticality === 'critical' ? 'bg-primary-subtle text-primary'
    : node.criticality === 'recommended' ? 'bg-accent-subtle text-accent'
    : 'bg-bg-muted text-text-muted'

  return (
    <div ref={setNodeRef} style={style}>
      {/* Row: always visible */}
      <div className={`flex items-center gap-0 px-2 py-1.5 rounded-md group transition-colors ${expanded ? 'bg-bg-subtle' : 'hover:bg-bg-muted'}`}>
        {/* Drag handle */}
        <button {...attributes} {...listeners} className="w-5 shrink-0 flex flex-col items-center gap-0.5 cursor-grab text-text-muted opacity-0 group-hover:opacity-100 transition-opacity" title="Arrastrar">
          <span className="block w-2.5 h-0.5 bg-current rounded-full" />
          <span className="block w-2.5 h-0.5 bg-current rounded-full" />
          <span className="block w-2.5 h-0.5 bg-current rounded-full" />
        </button>

        {/* Toggle */}
        <button type="button" onClick={onToggle} className="text-text-muted hover:text-text shrink-0">
          <ChevronIcon open={expanded} />
        </button>

        {/* Number dot (colored by criticality) */}
        <span className={`text-xs font-medium rounded-full w-5 h-5 flex items-center justify-center shrink-0 ml-1 ${critClass}`}>
          {index + 1}
        </span>

        {/* Title — editable, looks like text */}
        <input
          className="flex-1 min-w-0 text-sm font-medium text-text bg-transparent border-none focus:outline-none focus:ring-0 p-0 ml-2 focus:bg-bg focus:shadow-[0_0_0_1px_var(--color-primary)] focus:rounded focus:px-1 focus:-mx-1"
          value={node.title}
          onChange={(e) => onChange({ title: e.target.value })}
          placeholder="Titulo del nodo"
        />

        {/* Meta: prereq chips + time */}
        <div className="flex items-center gap-2 shrink-0 ml-2">
          {!expanded && node.prerequisites.length > 0 && (
            <div className="flex gap-0.5">
              {node.prerequisites.map(idx => (
                <span key={idx} className="w-4 h-4 rounded-full text-[9px] font-semibold border border-border text-text-muted flex items-center justify-center" title={`Depende de: ${nodes[idx]?.title || `Nodo ${idx + 1}`}`}>
                  {idx + 1}
                </span>
              ))}
            </div>
          )}
          <span className="text-xs text-text-muted whitespace-nowrap">{node.estimated_minutes} min</span>
          <button
            type="button"
            onClick={onDelete}
            className="text-text-muted hover:text-danger p-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
            title="Eliminar nodo"
          >
            <XIcon size={14} />
          </button>
        </div>
      </div>

      {/* Expanded children — tree indent with left border */}
      {expanded && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1, transition: { duration: duration.fast } }}
          className="ml-[42px] pl-4 border-l border-border space-y-1 pb-2"
        >
          {/* Summary */}
          <div className="flex items-start gap-0 px-2 py-1 rounded hover:bg-bg-muted">
            <span className="w-24 shrink-0 text-xs text-text-muted pt-0.5">Resumen</span>
            <textarea
              className="flex-1 min-w-0 text-sm text-text bg-transparent border-none focus:outline-none p-0 resize-none leading-relaxed focus:bg-bg focus:shadow-[0_0_0_1px_var(--color-primary)] focus:rounded focus:px-1.5 focus:py-0.5 focus:-mx-1.5 focus:-my-0.5"
              value={node.summary}
              onChange={(e) => onChange({ summary: e.target.value })}
              rows={1}
              onInput={(e) => { const t = e.target as HTMLTextAreaElement; t.style.height = 'auto'; t.style.height = t.scrollHeight + 'px' }}
            />
          </div>

          {/* Outcome */}
          <div className="flex items-start gap-0 px-2 py-1 rounded hover:bg-bg-muted">
            <span className="w-24 shrink-0 text-xs text-text-muted pt-0.5">Objetivo</span>
            <input
              className="flex-1 min-w-0 text-sm text-text bg-transparent border-none focus:outline-none p-0 focus:bg-bg focus:shadow-[0_0_0_1px_var(--color-primary)] focus:rounded focus:px-1.5 focus:-mx-1.5"
              value={node.outcome ?? ''}
              onChange={(e) => onChange({ outcome: e.target.value || null })}
              placeholder="Que sabra hacer el alumno"
            />
          </div>

          {/* Criticality */}
          <div className="flex items-center gap-0 px-2 py-1 rounded hover:bg-bg-muted">
            <span className="w-24 shrink-0 text-xs text-text-muted flex items-center">
              Importancia
              <InfoTooltip text="Imprescindible: el alumno debe dominar este tema para completar el curso. Recomendado: importante pero no obligatorio. Contexto: material complementario que enriquece pero no se evalua." />
            </span>
            <div className="flex gap-1">
              {CRITICALITY_OPTIONS.map(o => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => onChange({ criticality: o.value })}
                  className={`text-xs px-2.5 py-0.5 rounded-full border transition-colors ${
                    node.criticality === o.value
                      ? o.value === 'critical' ? 'bg-primary-subtle text-primary border-primary'
                        : o.value === 'recommended' ? 'bg-accent-subtle text-accent border-accent'
                        : 'bg-bg-muted text-text-muted border-border-strong'
                      : 'border-border text-text-muted hover:border-primary'
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>

          {/* Format */}
          <div className="flex items-center gap-0 px-2 py-1 rounded hover:bg-bg-muted">
            <span className="w-24 shrink-0 text-xs text-text-muted">Formato</span>
            <div className="flex gap-1">
              {FORMAT_OPTIONS.map(o => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => onChange({ default_ui_format: o.value })}
                  className={`text-xs px-2.5 py-0.5 rounded-full border transition-colors ${
                    node.default_ui_format === o.value
                      ? 'bg-primary-subtle text-primary border-primary'
                      : 'border-border text-text-muted hover:border-primary'
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>

          {/* Minutes */}
          <div className="flex items-center gap-0 px-2 py-1 rounded hover:bg-bg-muted">
            <span className="w-24 shrink-0 text-xs text-text-muted">Minutos</span>
            <input
              type="number"
              min={1}
              max={120}
              className="w-16 text-sm text-text bg-transparent border-none focus:outline-none p-0 focus:bg-bg focus:shadow-[0_0_0_1px_var(--color-primary)] focus:rounded focus:px-1.5 focus:-mx-1.5"
              value={node.estimated_minutes}
              onChange={(e) => onChange({ estimated_minutes: Number(e.target.value) || 1 })}
            />
          </div>

          {/* Prerequisites */}
          <div className="flex items-center gap-0 px-2 py-1 rounded hover:bg-bg-muted">
            <span className="w-24 shrink-0 text-xs text-text-muted">Depende de</span>
            <div className="flex flex-wrap gap-1">
              {node.prerequisites.map(idx => (
                <span key={idx} className="text-xs bg-primary-subtle text-primary px-2 py-0.5 rounded-full inline-flex items-center gap-1">
                  {idx + 1}. {nodes[idx]?.title ? nodes[idx].title.slice(0, 20) : `Nodo ${idx + 1}`}
                  <button type="button" onClick={() => onChange({ prerequisites: node.prerequisites.filter(p => p !== idx) })} className="opacity-60 hover:opacity-100">&times;</button>
                </span>
              ))}
              <button
                type="button"
                onClick={() => {
                  // Simple: add the first node that isn't already a prereq and isn't self
                  const available = nodes.map((_, j) => j).filter(j => j !== index && !node.prerequisites.includes(j))
                  if (available.length > 0) onChange({ prerequisites: [...node.prerequisites, available[0]] })
                }}
                className="text-xs border border-dashed border-border text-text-muted px-2 py-0.5 rounded-full hover:border-primary hover:text-primary transition-colors"
              >
                + Anadir
              </button>
            </div>
          </div>
        </motion.div>
      )}
    </div>
  )
}

// ── Schema content wrapper ──────────────────────────────────

function SchemaContent({
  proposing,
  proposeError,
  nodes,
  density,
  onDensityChange,
  totalMinutes,
  criticalCount,
  onNodeChange,
  onNodeDelete,
  onNodeAdd,
  onNodeReorder,
  onCreateCourse,
  creating,
  startError,
}: {
  proposing: boolean
  proposeError: string | null
  nodes: ProposedNode[]
  density: number
  onDensityChange: (v: number) => void
  totalMinutes: number
  criticalCount: number
  onNodeChange: (i: number, patch: Partial<ProposedNode>) => void
  onNodeDelete: (i: number) => void
  onNodeAdd: () => void
  onNodeReorder: (from: number, to: number) => void
  onCreateCourse: () => void
  creating: boolean
  startError: string | null
}) {
  const [expandedNodes, setExpandedNodes] = useState<Set<number>>(new Set())

  const toggleNode = (i: number) => {
    setExpandedNodes(prev => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i); else next.add(i)
      return next
    })
  }

  // Wrap onNodeDelete to also clean up expandedNodes indices
  const handleDelete = (deleted: number) => {
    onNodeDelete(deleted)
    setExpandedNodes(prev => {
      const next = new Set<number>()
      for (const idx of prev) {
        if (idx === deleted) continue
        next.add(idx > deleted ? idx - 1 : idx)
      }
      return next
    })
  }

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor),
  )
  const nodeIds = nodes.map((_, i) => `schema-node-${i}`)

  function handleDragEnd(event: { active: { id: string | number }; over: { id: string | number } | null }) {
    if (!event.over || event.active.id === event.over.id) return
    const from = nodeIds.indexOf(String(event.active.id))
    const to = nodeIds.indexOf(String(event.over.id))
    if (from !== -1 && to !== -1) {
      onNodeReorder(from, to)
      // Update expanded set to follow moved nodes
      setExpandedNodes(prev => {
        const arr = Array.from(prev)
        const next = new Set(arr.map(idx => {
          if (idx === from) return to
          if (from < to && idx > from && idx <= to) return idx - 1
          if (from > to && idx >= to && idx < from) return idx + 1
          return idx
        }))
        return next
      })
    }
  }

  if (proposing) {
    return (
      <div className="flex gap-6">
        <div className="shrink-0 space-y-4" style={{ width: 180 }}>
          <ShimmerSkeleton className="h-4 w-20" />
          <ShimmerSkeleton className="h-2 w-full rounded-full" />
          <div className="space-y-2">
            <ShimmerSkeleton className="h-3.5 w-full" />
            <ShimmerSkeleton className="h-3.5 w-full" />
            <ShimmerSkeleton className="h-3.5 w-full" />
          </div>
          <ShimmerSkeleton className="h-9 w-full rounded-md" />
        </div>
        <div className="flex-1 min-w-0">
          {Array.from({ length: 5 }).map((_, i) => <TreeNodeSkeleton key={i} opacity={1 - i * 0.15} />)}
        </div>
      </div>
    )
  }

  if (proposeError) {
    return (
      <div className="text-center py-12">
        <p className="text-sm text-danger mb-3">{proposeError}</p>
      </div>
    )
  }

  if (nodes.length === 0) {
    return (
      <div className="text-center py-12">
        <p className="text-sm text-text-muted">No se generaron nodos</p>
        <button type="button" onClick={onNodeAdd} className="mt-3 text-sm text-primary hover:underline">
          Anadir nodo manualmente
        </button>
      </div>
    )
  }

  return (
    <div className="flex gap-6">
      {/* Left sidebar */}
      <div className="shrink-0" style={{ width: 180 }}>
        <div className="space-y-5">
          <div>
            <label className="block text-xs font-medium text-text-muted uppercase tracking-wide mb-2">Densidad</label>
            <input type="range" min={1} max={5} step={1} value={density} onChange={(e) => onDensityChange(Number(e.target.value))} className="w-full accent-primary" />
            <div className="flex justify-between text-xs text-text-muted mt-1">
              <span>Breve</span><span>{density}</span><span>Detallado</span>
            </div>
          </div>

          <div className="space-y-2 text-sm">
            <div className="flex justify-between"><span className="text-text-muted">Nodos</span><span className="text-text font-medium">{nodes.length}</span></div>
            <div className="flex justify-between"><span className="text-text-muted">Imprescindibles</span><span className="text-text font-medium">{criticalCount}</span></div>
            <div className="flex justify-between"><span className="text-text-muted">Tiempo est.</span><span className="text-text font-medium">{totalMinutes} min</span></div>
          </div>

          {startError && <p className="text-xs text-danger">{startError}</p>}

          <Button variant="primary" className="w-full" onClick={onCreateCourse} disabled={creating || nodes.length === 0}>
            {creating ? 'Creando...' : 'Crear curso'}
          </Button>
        </div>
      </div>

      {/* Right: tree */}
      <div className="flex-1 min-w-0">
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={nodeIds} strategy={verticalListSortingStrategy}>
            <AnimatePresence initial={false}>
              {nodes.map((node, i) => (
                <motion.div
                  key={`node-${node._key}`}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0, transition: { duration: duration.normal, ease: ease.base, delay: i * 0.04 } }}
                  exit={{ opacity: 0, x: -32, transition: { duration: duration.fast, ease: ease.snapOut } }}
                >
                  <SortableTreeNode
                    id={nodeIds[i]}
                    index={i}
                    node={node}
                    nodes={nodes}
                    expanded={expandedNodes.has(i)}
                    onToggle={() => toggleNode(i)}
                    onChange={(patch) => onNodeChange(i, patch)}
                    onDelete={() => handleDelete(i)}
                  />
                </motion.div>
              ))}
            </AnimatePresence>
          </SortableContext>
        </DndContext>

        {/* Add node */}
        <button
          type="button"
          onClick={onNodeAdd}
          className="w-full mt-2 px-2 py-1.5 rounded-md text-sm text-text-muted hover:text-primary hover:bg-bg-muted transition-colors flex items-center gap-2"
        >
          <PlusIcon size={14} />
          Anadir nodo
        </button>
      </div>
    </div>
  )
}

// ── Delivery mode selector ───────────────────────────────────

function DeliverySelector({ value, onChange }: { value: DeliveryChoice; onChange: (v: DeliveryChoice) => void }) {
  const options: { key: DeliveryChoice; label: string; desc: string }[] = [
    { key: 'dynamic', label: 'Personalizado', desc: 'La IA adapta el contenido a cada alumno' },
    { key: 'static', label: 'Clasico', desc: 'Genera el curso una vez, igual para todos' },
  ]

  return (
    <div>
      <label className="block text-sm font-medium text-text mb-2">Modo</label>
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
