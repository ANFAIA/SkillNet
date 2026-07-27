import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { ease, duration } from '../../lib/motion'
import { Card, CardTitle, Button, Input, Badge, EmptyState, FileUploadZone, ProgressBar, StepIndicator } from '../../components/ui'
import { GenerationProgress } from '../../components/generation/GenerationProgress'
import { useUploadDocument, useProcessDocument } from '../../api/documents'
import { useCreateCourse, useGenerateContent, usePublishCourse, useCourse, useUpdateLesson, useUpdateExercise } from '../../api/courses'
import { useGenerationProgress, useGenerationJobStatus, jobToProgress } from '../../api/generation'
import { useDynamicCoursesMode } from '../../api/health'
import { useUsers } from '../../api/users'
import { useAssignCourse } from '../../api/enrollments'
import { ApiError } from '../../api/client'
import type { GenerationProgress as GenProgress, User, Lesson, Exercise } from '../../types'

type SourceType = 'documentos' | 'cero' | 'catalogo' | null
type Direction = 1 | -1

const stepLabels = ['Origen', 'Contenido', 'Generando', 'Revisar', 'Asignar']

function FileIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  )
}
function GridIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" />
    </svg>
  )
}
function EditIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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

// --- Step 0: Source ---
function StepSource({ selected, onSelect }: { selected: SourceType; onSelect: (s: SourceType) => void }) {
  const sources: { key: SourceType; title: string; desc: string; icon: React.ReactNode; disabled?: boolean }[] = [
    { key: 'documentos', title: 'Documentos', desc: 'Sube un PDF y generamos el curso con IA', icon: <FileIcon /> },
    { key: 'cero', title: 'Desde cero', desc: 'Define el tema y generamos el contenido con IA', icon: <EditIcon /> },
    { key: 'catalogo', title: 'Catalogo', desc: 'Proximamente', icon: <GridIcon />, disabled: true },
  ]

  return (
    <div>
      <h3 className="text-base font-medium text-text">Elige el origen del curso</h3>
      <p className="text-sm text-text-secondary mt-1">Selecciona como quieres crear el contenido</p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-5">
        {sources.map((s) => (
          <Card
            key={s.key}
            variant="default"
            className={`transition-colors ${
              s.disabled
                ? 'opacity-50 cursor-not-allowed'
                : selected === s.key
                  ? 'border-primary bg-primary-subtle cursor-pointer'
                  : 'cursor-pointer hover:border-primary'
            }`}
            onClick={() => !s.disabled && onSelect(s.key)}
          >
            <div className="text-text-secondary mb-3">{s.icon}</div>
            <p className="text-sm font-medium text-text">{s.title}</p>
            <p className="text-xs text-text-muted mt-1">{s.desc}</p>
          </Card>
        ))}
      </div>
    </div>
  )
}

// --- Step 1: Content ---
function StepContent({
  source, title, onTitleChange, uploader, documentReady,
}: {
  source: SourceType
  title: string
  onTitleChange: (v: string) => void
  uploader: ReturnType<typeof useUploadDocument>
  documentReady: boolean
}) {
  return (
    <div>
      <h3 className="text-base font-medium text-text">Contenido del curso</h3>
      <p className="text-sm text-text-secondary mt-1">
        {source === 'documentos' ? 'Sube tu documento y dale un nombre al curso' : 'Describe el curso que quieres generar'}
      </p>

      <div className="mt-5 space-y-4">
        <Input label="Nombre del curso" placeholder="Ej: Seguridad Alimentaria" value={title} onChange={(e) => onTitleChange(e.target.value)} />

        {source === 'documentos' && (
          <div>
            <label className="block text-sm font-medium text-text mb-1">Documento</label>
            <FileUploadZone
              accept=".pdf,.docx,.md,.txt"
              maxSizeMB={20}
              onFilesSelected={(files) => uploader.uploadFile(files[0]).catch(() => {})}
            />
            {uploader.uploads.length > 0 && (
              <div className="mt-3 space-y-2">
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
                    {(u.status === 'processing' || u.status === 'ready') && (
                      <p className="text-xs text-text-muted mt-0.5">Documento listo</p>
                    )}
                  </div>
                ))}
              </div>
            )}
            {!documentReady && <p className="text-xs text-text-muted mt-2">Sube un documento para continuar.</p>}
          </div>
        )}
      </div>
    </div>
  )
}

// --- Inline editable lesson ---
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

  function cancelTitle() {
    setTitleDraft(lesson.title)
    setEditingTitle(false)
  }

  function saveContent() {
    if (contentDraft !== lesson.content) {
      updateLesson.mutate({ lessonId: lesson.id, payload: { content: contentDraft } })
    }
    setEditingContent(false)
  }

  function cancelContent() {
    setContentDraft(lesson.content)
    setEditingContent(false)
  }

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
            <button type="button" onClick={saveTitle} className="text-accent hover:text-accent/80 p-0.5" title="Guardar"><SaveIcon /></button>
            <button type="button" onClick={cancelTitle} className="text-text-muted hover:text-text p-0.5" title="Cancelar"><XIcon /></button>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 flex-1 min-w-0 group">
            <span className="text-text-secondary truncate min-w-0">{lesson.title}</span>
            <button type="button" onClick={() => { setTitleDraft(lesson.title); setEditingTitle(true) }} className="text-text-muted hover:text-primary opacity-0 group-hover:opacity-100 transition-opacity p-0.5 shrink-0" title="Editar titulo">
              <PencilIcon />
            </button>
          </div>
        )}
      </div>

      {expanded && (
        <div className="mt-3 ml-6">
          <div className="mb-2">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-medium text-text-muted uppercase tracking-wide">Contenido</span>
              {!editingContent && (
                <button type="button" onClick={() => { setContentDraft(lesson.content); setEditingContent(true) }} className="text-text-muted hover:text-primary p-0.5" title="Editar contenido">
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
                    {updateLesson.isPending ? 'Guardando...' : 'Guardar'}
                  </Button>
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
                {lesson.exercises.map((ex) => (
                  <EditableExercise key={ex.id} exercise={ex} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </li>
  )
}

// --- Inline editable exercise ---
function EditableExercise({ exercise }: { exercise: Exercise }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(() => JSON.stringify(exercise.content, null, 2))
  const updateExercise = useUpdateExercise()

  function save() {
    try {
      const parsed = JSON.parse(draft)
      updateExercise.mutate({ exerciseId: exercise.id, payload: { content: parsed } })
      setEditing(false)
    } catch {
      // invalid JSON, don't save
    }
  }

  function cancel() {
    setDraft(JSON.stringify(exercise.content, null, 2))
    setEditing(false)
  }

  const label = exercise.type.replace(/_/g, ' ')

  return (
    <div className="border border-border/50 rounded p-2 bg-bg-subtle">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <Badge variant="primary" badgeStyle="plain">{label}</Badge>
          <span className="text-xs text-text-muted truncate min-w-0">
            {(exercise.content as unknown as Record<string, unknown>).question as string
              ?? (exercise.content as unknown as Record<string, unknown>).statement as string
              ?? (exercise.content as unknown as Record<string, unknown>).instruction as string
              ?? (exercise.content as unknown as Record<string, unknown>).context as string
              ?? ''}
          </span>
        </div>
        {!editing && (
          <button type="button" onClick={() => { setDraft(JSON.stringify(exercise.content, null, 2)); setEditing(true) }} className="text-text-muted hover:text-primary p-0.5 shrink-0" title="Editar ejercicio">
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
              {updateExercise.isPending ? 'Guardando...' : 'Guardar'}
            </Button>
            <Button size="sm" variant="secondary" onClick={cancel}>Cancelar</Button>
          </div>
        </div>
      )}
    </div>
  )
}

// --- Step 3: Review ---
function StepReview({ courseId, onPublish, publishing, published }: { courseId: string; onPublish: () => void; publishing: boolean; published: boolean }) {
  const { data: course, isLoading } = useCourse(courseId)

  if (isLoading) return <p className="text-sm text-text-secondary">Cargando contenido generado...</p>
  if (!course) return <EmptyState title="No se pudo cargar el curso generado" />

  const totalLessons = course.modules.reduce((acc, m) => acc + m.lessons.length, 0)

  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-medium text-text">Revisa y edita el contenido generado</h3>
          <p className="text-sm text-text-secondary mt-1">{course.modules.length} modulos · {totalLessons} lecciones</p>
        </div>
        <Button size="sm" variant="accent" onClick={onPublish} disabled={publishing || published}>
          {published ? 'Publicado' : publishing ? 'Publicando...' : 'Publicar'}
        </Button>
      </div>

      <div className="mt-5 space-y-3">
        {course.modules.map((mod, i) => (
          <Card key={mod.id}>
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="truncate min-w-0">Modulo {i + 1}: {mod.title}</CardTitle>
              <Badge variant="accent" badgeStyle="plain">{mod.lessons.length} lecciones</Badge>
            </div>
            <ul className="mt-3 space-y-2">
              {mod.lessons.map((l) => (
                <EditableLesson key={l.id} lesson={l} />
              ))}
            </ul>
          </Card>
        ))}
      </div>
    </div>
  )
}

// --- Step 4: Assign ---
function StepAssign({ selected, onToggle, deadline, onDeadline }: {
  selected: Set<string>
  onToggle: (id: string) => void
  deadline: string
  onDeadline: (v: string) => void
}) {
  const { data, isLoading } = useUsers({ role: 'employee' })
  const employees: User[] = data?.items ?? []

  return (
    <div>
      <h3 className="text-base font-medium text-text">Asignar a empleados</h3>
      <p className="text-sm text-text-secondary mt-1">Selecciona quienes tomaran este curso</p>

      <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-text mb-2">Empleados</label>
          <div className="border border-border rounded-lg max-h-64 overflow-y-auto">
            {isLoading ? (
              <p className="text-sm text-text-muted p-4">Cargando...</p>
            ) : employees.length === 0 ? (
              <p className="text-sm text-text-muted p-4">No hay empleados.</p>
            ) : (
              employees.map((emp) => (
                <label key={emp.id} className="flex items-center gap-3 px-4 py-2.5 border-b border-border last:border-b-0 hover:bg-bg-subtle cursor-pointer transition-colors">
                  <input type="checkbox" checked={selected.has(emp.id)} onChange={() => onToggle(emp.id)} className="accent-primary" />
                  <div className="min-w-0">
                    <p className="text-sm text-text truncate">{emp.full_name}</p>
                    <p className="text-xs text-text-muted truncate">{emp.email}</p>
                  </div>
                </label>
              ))
            )}
          </div>
          <p className="text-xs text-text-muted mt-1">{selected.size} seleccionados</p>
        </div>

        <div>
          <Input label="Fecha limite (opcional)" type="date" value={deadline} onChange={(e) => onDeadline(e.target.value)} />
        </div>
      </div>
    </div>
  )
}

// Wizard step slide — blur + signature curve, with iOS-style asymmetry:
// entering a step is deliberate (slow, snapIn), leaving is quick (fast, snapOut).
const slideVariants = {
  enter: (dir: Direction) => ({ x: dir > 0 ? 200 : -200, opacity: 0, filter: 'blur(6px)' }),
  center: {
    x: 0,
    opacity: 1,
    filter: 'blur(0px)',
    transition: { duration: 0.4, ease: ease.snapIn },
  },
  exit: (dir: Direction) => ({
    x: dir > 0 ? -200 : 200,
    opacity: 0,
    filter: 'blur(6px)',
    transition: { duration: duration.fast, ease: ease.snapOut },
  }),
}

export function CreateCourse() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)
  const [direction, setDirection] = useState<Direction>(1)

  const [source, setSource] = useState<SourceType>(null)
  const [title, setTitle] = useState('')
  const [documentId, setDocumentId] = useState<string | null>(null)
  const [courseId, setCourseId] = useState<string | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)
  const [startError, setStartError] = useState<string | null>(null)
  const [published, setPublished] = useState(false)

  const [assignSelected, setAssignSelected] = useState<Set<string>>(new Set())
  const [deadline, setDeadline] = useState('')

  const uploader = useUploadDocument()
  const processDoc = useProcessDocument()
  const createCourse = useCreateCourse()
  const generate = useGenerateContent()
  const publish = usePublishCourse()
  const assign = useAssignCourse()

  /**
   * The v2 branch of step 1 (§13, B10). With the flag in `shadow` or `on` the creator
   * can define a schema instead of generating a course in one shot, and the schema
   * screen is where nodes get reviewed and validated before anything is generated.
   *
   * It is an **extra** action, not a replacement: the v1 "Generar" button is still
   * right there, so with the flag off (or for a course built from scratch, where
   * there is no source document for the designer to read) the wizard behaves exactly
   * as it does today.
   */
  const { mode: dynamicMode } = useDynamicCoursesMode()
  const schemaFirstAvailable =
    (dynamicMode === 'shadow' || dynamicMode === 'on') &&
    source === 'documentos' &&
    !!documentId

  // Mark the uploaded document ready + kick off server-side processing.
  const latestUpload = uploader.uploads[uploader.uploads.length - 1]
  useEffect(() => {
    if (latestUpload?.status === 'processing' && latestUpload.documentId && latestUpload.documentId !== documentId) {
      setDocumentId(latestUpload.documentId)
      processDoc.mutate(latestUpload.documentId)
      uploader.markReady(latestUpload.documentId)
    }
  }, [latestUpload, documentId, processDoc, uploader])

  const documentReady = source !== 'documentos' || !!documentId

  // Generation tracking (SSE + polling fallback).
  const { progress: sseProgress, connectionFailed } = useGenerationProgress(step === 2 ? jobId : null)
  const { data: polledJob } = useGenerationJobStatus(step === 2 && connectionFailed ? jobId : null)
  const effective: GenProgress = connectionFailed && polledJob ? jobToProgress(polledJob) : sseProgress

  // Advance to review once generation publishes.
  useEffect(() => {
    if (step === 2 && effective.step === 'published') {
      if (effective.courseId) setCourseId(effective.courseId)
      setPublished(true)
      setDirection(1)
      setStep(3)
    }
  }, [step, effective.step, effective.courseId])

  async function startGeneration() {
    setStartError(null)
    try {
      const course = await createCourse.mutateAsync({
        title: title.trim(),
        source_document_id: documentId ?? undefined,
      })
      setCourseId(course.id)
      const job = await generate.mutateAsync({
        courseId: course.id,
        source_document_id: documentId ?? undefined,
        output_type: 'course_and_manual',
      })
      setJobId(job.job_id)
      setDirection(1)
      setStep(2)
    } catch (err) {
      setStartError(err instanceof ApiError ? err.body.detail : 'No se pudo iniciar la generacion')
    }
  }

  // Creates the course and hands over to the schema screen. It deliberately does not
  // call `schema/propose` here: the proposal needs `intent_density`, which is chosen on
  // that screen, and starting a designer run from behind this button would spend an LLM
  // call on a density the creator never saw.
  async function startSchemaDefinition() {
    setStartError(null)
    try {
      const course = await createCourse.mutateAsync({
        title: title.trim(),
        source_document_id: documentId ?? undefined,
      })
      navigate(`/admin/curso/${course.id}/esquema`)
    } catch (err) {
      setStartError(err instanceof ApiError ? err.body.detail : 'No se pudo crear el curso')
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
    if (assignSelected.size === 0) {
      navigate('/admin/contenido')
      return
    }
    assign.mutate(
      { user_ids: Array.from(assignSelected), course_id: courseId, deadline: deadline || undefined },
      { onSuccess: () => navigate('/admin/contenido') },
    )
  }

  function canNext(): boolean {
    switch (step) {
      case 0: return source === 'documentos' || source === 'cero'
      case 1: return title.trim().length > 0 && documentReady
      case 3: return true
      default: return false
    }
  }

  function next() {
    if (step === 1) {
      void startGeneration()
      return
    }
    if (step === 3) {
      setDirection(1)
      setStep(4)
      return
    }
    if (step < 4 && canNext()) {
      setDirection(1)
      setStep(step + 1)
    }
  }

  function prev() {
    // No going back from generation / after it started.
    if (step === 0 || step >= 2) return
    setDirection(-1)
    setStep(step - 1)
  }

  function renderStep() {
    switch (step) {
      case 0: return <StepSource selected={source} onSelect={setSource} />
      case 1: return <StepContent source={source} title={title} onTitleChange={setTitle} uploader={uploader} documentReady={documentReady} />
      case 2: return (
        <div className="py-6">
          <div className="text-center mb-8">
            <h3 className="text-base font-medium text-text">{effective.step === 'failed' ? 'La generacion fallo' : 'Generando curso...'}</h3>
            <p className="text-sm text-text-secondary mt-1">Esto puede tomar unos momentos</p>
          </div>
          <GenerationProgress progress={effective} />
          {effective.step === 'failed' && (
            <div className="mt-6 text-center">
              <Button variant="secondary" onClick={() => { setStep(1); setJobId(null) }}>Volver a intentar</Button>
            </div>
          )}
        </div>
      )
      case 3: return courseId ? <StepReview courseId={courseId} onPublish={handlePublish} publishing={publish.isPending} published={published} /> : null
      case 4: return <StepAssign selected={assignSelected} onToggle={toggleAssign} deadline={deadline} onDeadline={setDeadline} />
      default: return null
    }
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-text">Crear Curso</h2>
          <p className="text-sm text-text-secondary mt-1">{stepLabels[step]}</p>
        </div>
        <StepIndicator current={step} total={5} />
      </div>

      <div className="mt-6 overflow-hidden">
        <AnimatePresence mode="wait" custom={direction} initial={false}>
          <motion.div key={step} custom={direction} variants={slideVariants} initial="enter" animate="center" exit="exit">
            {renderStep()}
          </motion.div>
        </AnimatePresence>
      </div>

      {startError && step === 1 && <p className="text-sm text-danger mt-3">{startError}</p>}

      {step !== 2 && (
        <div className="flex items-center justify-between mt-8 pt-4 border-t border-border">
          <div>
            {step === 1 && (
              <Button variant="secondary" onClick={prev}>Anterior</Button>
            )}
          </div>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            {step === 1 && schemaFirstAvailable && (
              <Button
                variant="secondary"
                onClick={() => void startSchemaDefinition()}
                disabled={!canNext() || createCourse.isPending || generate.isPending}
                title="Define y revisa el esquema antes de generar nada"
              >
                Definir esquema
              </Button>
            )}
            {step < 3 ? (
              <Button variant="primary" onClick={next} disabled={!canNext() || createCourse.isPending || generate.isPending}>
                {step === 1 ? (createCourse.isPending || generate.isPending ? 'Iniciando...' : 'Generar') : 'Siguiente'}
              </Button>
            ) : step === 3 ? (
              <Button variant="primary" onClick={next}>Siguiente</Button>
            ) : (
              <Button variant="accent" onClick={finish} disabled={assign.isPending}>
                {assign.isPending ? 'Asignando...' : assignSelected.size > 0 ? 'Asignar y finalizar' : 'Finalizar'}
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
