import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Card, CardTitle, Button, Input, Badge, EmptyState, FileUploadZone, ProgressBar } from '../../components/ui'
import { GenerationProgress } from '../../components/generation/GenerationProgress'
import { useUploadDocument, useProcessDocument } from '../../api/documents'
import { useCreateCourse, useGenerateContent, usePublishCourse, useCourse } from '../../api/courses'
import { useGenerationProgress, useGenerationJobStatus, jobToProgress } from '../../api/generation'
import { useUsers } from '../../api/users'
import { useAssignCourse } from '../../api/enrollments'
import { ApiError } from '../../api/client'
import type { GenerationProgress as GenProgress, User } from '../../types'

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

function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center gap-1 sm:gap-2">
      {Array.from({ length: total }).map((_, i) => (
        <div key={i} className="flex items-center gap-1 sm:gap-2">
          <div
            className={`w-6 h-6 sm:w-7 sm:h-7 rounded-full flex items-center justify-center text-xs font-medium transition-colors shrink-0 ${
              i < current ? 'bg-accent text-white' : i === current ? 'bg-primary text-white' : 'bg-bg-muted text-text-muted'
            }`}
          >
            {i < current ? <CheckIcon /> : i + 1}
          </div>
          {i < total - 1 && (
            <div className={`w-4 sm:w-8 h-px transition-colors ${i < current ? 'bg-accent' : 'bg-border'}`} />
          )}
        </div>
      ))}
    </div>
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
            variant={s.disabled ? 'default' : 'interactive'}
            className={`${selected === s.key ? 'border-primary bg-primary-subtle' : ''} ${s.disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
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
          <h3 className="text-base font-medium text-text">Revisa el contenido generado</h3>
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
            <ul className="mt-2 space-y-1">
              {mod.lessons.map((l) => (
                <li key={l.id} className="text-sm text-text-secondary flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-border shrink-0" />
                  {l.title}
                </li>
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

const slideVariants = {
  enter: (dir: Direction) => ({ x: dir > 0 ? 200 : -200, opacity: 0 }),
  center: { x: 0, opacity: 1 },
  exit: (dir: Direction) => ({ x: dir > 0 ? -200 : 200, opacity: 0 }),
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
        <AnimatePresence mode="wait" custom={direction}>
          <motion.div key={step} custom={direction} variants={slideVariants} initial="enter" animate="center" exit="exit" transition={{ duration: 0.2, ease: 'easeOut' }}>
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
          <div>
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
