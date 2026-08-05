import { useEffect, useState, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence, LayoutGroup, useInstantLayoutTransition } from 'framer-motion'
import { ease, duration } from '../../lib/motion'
import { Button, Input, Textarea, Badge, EmptyState, FileUploadZone, ProgressBar } from '../../components/ui'
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

type SourceType = 'documentos' | 'cero' | null
type DeliveryChoice = 'dynamic' | 'static'
type Phase = 'choose' | 'details' | 'schema' | 'generating' | 'review' | 'assign'

interface ProposedNode {
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
  exit: { opacity: 0, transition: { duration: 0.2, ease: ease.base } },
}
const innerFadeIn = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: 0.3, ease: ease.base } },
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
    if (source === 'documentos' && latestUpload?.file.name && !title) {
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
      const result = await post<{ nodes: ProposedNode[] }>('/ai/schema-propose', {
        title: title.trim(),
        description: idea.trim() || undefined,
        intent_density: d,
      })
      if (!abort.signal.aborted) {
        setProposedNodes(result.nodes)
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
  }, [title, idea])

  // Auto-propose when entering schema phase for the first time (no nodes yet)
  const prevPhaseRef = useRef<Phase>('choose')
  useEffect(() => {
    if (phase === 'schema' && prevPhaseRef.current === 'details' && proposedNodes.length === 0) {
      void proposeSchema(density)
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
    if (source !== 'cero') return undefined
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
      const sourceId = source === 'documentos' ? documentId ?? undefined : undefined
      const course = await createCourse.mutateAsync({
        title: title.trim(),
        description: idea.trim() || undefined,
        source_document_id: sourceId,
      })
      setCourseId(course.id)

      // Save the proposed nodes as the course schema
      const schemaNodes = proposedNodes.map((n, i) => ({
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
        prerequisite_node_ids: [],
        archived: false,
      }))
      await put(`/courses/${course.id}/schema`, {
        intent_density: density,
        nodes: schemaNodes,
      })

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

  const busyStarting = writingSource || createCourse.isPending || generate.isPending
  const documentReady = source !== 'documentos' || !!documentId
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
        <div className="flex items-center gap-3 mb-8">
          <h2 className="text-xl font-semibold text-text">Asignar empleados</h2>
        </div>
        <StepAssign selected={assignSelected} onToggle={toggleAssign} deadline={deadline} onDeadline={setDeadline} />
        <div className="flex justify-end mt-8 pt-5 border-t border-border">
          <Button variant="accent" onClick={finish} disabled={assign.isPending}>
            {assign.isPending ? 'Asignando...' : assignSelected.size > 0 ? 'Asignar y finalizar' : 'Finalizar'}
          </Button>
        </div>
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
                / {source === 'documentos' ? 'Documento' : 'Idea'}
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

          {/* Card: Documentos */}
          {(activeCard === 'documentos' || !expanded) && (
            <motion.div
              layoutId="source-card-documentos"
              transition={morphTransition.layout}
              style={{ borderRadius: 8 }}
              className={`border p-6 ${
                expanded
                  ? 'border-primary bg-bg'
                  : source === 'documentos'
                    ? 'border-primary bg-primary-subtle cursor-pointer'
                    : 'border-border hover:border-primary cursor-pointer'
              }`}
              onClick={() => { if (!expanded) setSource(source === 'documentos' ? null : 'documentos') }}
            >
              {!expanded ? (
                <motion.div key="doc-col" {...contentReveal}>
                  <div className="flex flex-col items-center justify-center text-center px-4 py-8">
                    <div className="text-text-muted mb-4"><FileIcon /></div>
                    <p className="text-sm font-medium text-text">Tengo un documento</p>
                    <p className="text-xs text-text-muted mt-1.5">PDF, Word, Markdown o texto plano</p>
                  </div>
                </motion.div>
              ) : (
                <AnimatePresence mode="wait">
                  {phase === 'details' ? (
                    <motion.div key="doc-details" {...innerFadeIn} {...innerFadeOut}>
                      <div className="flex items-center gap-3 mb-6">
                        <div className="text-primary"><FileIcon /></div>
                        <div>
                          <p className="text-sm font-medium text-text">A partir de un documento</p>
                          <p className="text-xs text-text-muted">Sube el archivo y ponle nombre al curso</p>
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
                              <div key={i} className="text-sm">
                                <div className="flex items-center justify-between gap-2">
                                  <span className="text-text truncate min-w-0">{u.file.name}</span>
                                  {u.status === 'ready' || u.status === 'processing' ? (
                                    <span className="text-accent shrink-0"><CheckIcon /></span>
                                  ) : u.status === 'error' ? (
                                    <span className="text-danger text-xs shrink-0">{u.error}</span>
                                  ) : null}
                                </div>
                                {u.status === 'uploading' && <ProgressBar value={u.progress} size="sm" className="mt-1" />}
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
                    <motion.div key="doc-schema" {...innerFadeIn} {...innerFadeOut}>
                      <SchemaContent
                        proposing={proposing}
                        proposeError={proposeError}
                        nodes={proposedNodes}
                        density={density}
                        onDensityChange={handleDensityChange}
                        totalMinutes={totalMinutes}
                        criticalCount={criticalCount}
                        title={title}
                        onNodeTitleChange={(i, v) => setProposedNodes(ns => ns.map((n, j) => j === i ? { ...n, title: v } : n))}
                        onNodeDelete={(i) => setProposedNodes(ns => ns.filter((_, j) => j !== i))}
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

          {/* Card: Desde cero */}
          {(activeCard === 'cero' || !expanded) && (
            <motion.div
              layoutId="source-card-cero"
              transition={morphTransition.layout}
              style={{ borderRadius: 8 }}
              className={`border p-6 ${
                expanded
                  ? 'border-primary bg-bg'
                  : source === 'cero'
                    ? 'border-primary bg-primary-subtle cursor-pointer'
                    : 'border-border hover:border-primary cursor-pointer'
              }`}
              onClick={() => { if (!expanded) setSource(source === 'cero' ? null : 'cero') }}
            >
              {!expanded ? (
                <motion.div key="cero-col" {...contentReveal}>
                  <div className="flex flex-col items-center justify-center text-center px-4 py-8">
                    <div className="text-text-muted mb-4"><EditIcon /></div>
                    <p className="text-sm font-medium text-text">Tengo una idea</p>
                    <p className="text-xs text-text-muted mt-1.5">Describe el tema y la IA escribe el contenido</p>
                  </div>
                </motion.div>
              ) : (
                <AnimatePresence mode="wait">
                  {phase === 'details' ? (
                    <motion.div key="cero-details" {...innerFadeIn} {...innerFadeOut}>
                      <div className="flex items-center gap-3 mb-6">
                        <div className="text-primary"><EditIcon /></div>
                        <div>
                          <p className="text-sm font-medium text-text">A partir de una idea</p>
                          <p className="text-xs text-text-muted">La IA escribe un documento fuente del que sale el curso</p>
                        </div>
                      </div>
                      <div className="space-y-5">
                        <Input label="Nombre del curso" placeholder="Ej: Seguridad Alimentaria" value={title} onChange={(e) => setTitle(e.target.value)} />
                        <Textarea
                          label="Que quieres que cubra (opcional)"
                          placeholder="Ej: como funciona una sinapsis, los neurotransmisores principales y la plasticidad. Nivel introductorio."
                          hint="Con esto la IA escribe un documento fuente, editable despues, del que sale el curso."
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
                    <motion.div key="cero-schema" {...innerFadeIn} {...innerFadeOut}>
                      <SchemaContent
                        proposing={proposing}
                        proposeError={proposeError}
                        nodes={proposedNodes}
                        density={density}
                        onDensityChange={handleDensityChange}
                        totalMinutes={totalMinutes}
                        criticalCount={criticalCount}
                        title={title}
                        onNodeTitleChange={(i, v) => setProposedNodes(ns => ns.map((n, j) => j === i ? { ...n, title: v } : n))}
                        onNodeDelete={(i) => setProposedNodes(ns => ns.filter((_, j) => j !== i))}
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

function SchemaContent({
  proposing,
  proposeError,
  nodes,
  density,
  onDensityChange,
  totalMinutes,
  criticalCount,
  title,
  onNodeTitleChange,
  onNodeDelete,
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
  title: string
  onNodeTitleChange: (i: number, v: string) => void
  onNodeDelete: (i: number) => void
  onCreateCourse: () => void
  creating: boolean
  startError: string | null
}) {
  if (proposing) {
    return (
      <div className="text-center py-12">
        <p className="text-sm font-medium text-text">Disenando el esquema...</p>
        <p className="text-xs text-text-muted mt-2">{title}</p>
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
      </div>
    )
  }

  return (
    <div className="flex gap-6">
      {/* Left sidebar: density + stats + create button */}
      <div className="shrink-0" style={{ width: 200 }}>
        <div className="space-y-5">
          <div>
            <label className="block text-xs font-medium text-text-muted uppercase tracking-wide mb-2">Densidad</label>
            <input
              type="range"
              min={1}
              max={5}
              step={1}
              value={density}
              onChange={(e) => onDensityChange(Number(e.target.value))}
              className="w-full accent-primary"
            />
            <div className="flex justify-between text-xs text-text-muted mt-1">
              <span>Breve</span>
              <span>{density}</span>
              <span>Detallado</span>
            </div>
          </div>

          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-text-muted">Nodos</span>
              <span className="text-text font-medium">{nodes.length}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Imprescindibles</span>
              <span className="text-text font-medium">{criticalCount}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-text-muted">Tiempo est.</span>
              <span className="text-text font-medium">{totalMinutes} min</span>
            </div>
          </div>

          {startError && <p className="text-xs text-danger">{startError}</p>}

          <Button
            variant="primary"
            className="w-full"
            onClick={onCreateCourse}
            disabled={creating || nodes.length === 0}
          >
            {creating ? 'Creando...' : 'Crear curso'}
          </Button>
        </div>
      </div>

      {/* Right: node list */}
      <div className="flex-1 min-w-0 space-y-3">
        {nodes.map((node, i) => (
          <div
            key={i}
            className="border border-border rounded-lg p-4 flex items-start gap-4"
            style={{ borderRadius: 8 }}
          >
            <span className="text-xs font-medium text-text-muted bg-bg-muted rounded-full w-6 h-6 flex items-center justify-center shrink-0 mt-0.5">
              {i + 1}
            </span>
            <div className="flex-1 min-w-0">
              <input
                className="w-full text-sm font-medium text-text bg-transparent border-none focus:outline-none focus:ring-0 p-0"
                value={node.title}
                onChange={(e) => onNodeTitleChange(i, e.target.value)}
              />
              <p className="text-xs text-text-muted mt-0.5">{node.summary}</p>
              <div className="flex items-center gap-2 mt-2">
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  node.criticality === 'critical' ? 'bg-primary-subtle text-primary'
                  : node.criticality === 'recommended' ? 'bg-accent-subtle text-accent'
                  : 'bg-bg-muted text-text-muted'
                }`}>
                  {node.criticality === 'critical' ? 'Imprescindible'
                   : node.criticality === 'recommended' ? 'Recomendado'
                   : 'Contexto'}
                </span>
                {node.estimated_minutes > 0 && (
                  <span className="text-xs text-text-muted">{node.estimated_minutes} min</span>
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={() => onNodeDelete(i)}
              className="text-text-muted hover:text-danger p-1 shrink-0"
              title="Eliminar nodo"
            >
              <XIcon size={16} />
            </button>
          </div>
        ))}
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
