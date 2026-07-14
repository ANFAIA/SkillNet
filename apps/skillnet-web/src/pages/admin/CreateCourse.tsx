import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Card, CardTitle, Button, Input, Badge, ProgressBar } from '../../components/ui'
import { employees } from '../../data/adminMockData'

type SourceType = 'documentos' | 'catalogo' | 'cero' | null
type Direction = 1 | -1

const stepLabels = ['Origen', 'Contenido', 'Generando', 'Revisar', 'Asignar']

// --- Icons ---

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
      <rect x="3" y="3" width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
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

function UploadIcon() {
  return (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
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

// --- Step Indicator ---

function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center gap-1 sm:gap-2">
      {Array.from({ length: total }).map((_, i) => (
        <div key={i} className="flex items-center gap-1 sm:gap-2">
          <div
            className={`w-6 h-6 sm:w-7 sm:h-7 rounded-full flex items-center justify-center text-xs font-medium transition-colors shrink-0 ${
              i < current
                ? 'bg-accent text-white'
                : i === current
                ? 'bg-primary text-white'
                : 'bg-bg-muted text-text-muted'
            }`}
          >
            {i < current ? <CheckIcon /> : i + 1}
          </div>
          {i < total - 1 && (
            <div
              className={`w-4 sm:w-8 h-px transition-colors ${
                i < current ? 'bg-accent' : 'bg-border'
              }`}
            />
          )}
        </div>
      ))}
    </div>
  )
}

// --- Step Components ---

function StepSource({
  selected,
  onSelect,
}: {
  selected: SourceType
  onSelect: (s: SourceType) => void
}) {
  const sources: { key: SourceType; title: string; desc: string; icon: React.ReactNode }[] = [
    { key: 'documentos', title: 'Documentos', desc: 'Sube PDFs, presentaciones o documentos internos', icon: <FileIcon /> },
    { key: 'catalogo', title: 'Catalogo', desc: 'Elige de nuestro catalogo de cursos predefinidos', icon: <GridIcon /> },
    { key: 'cero', title: 'Desde cero', desc: 'Define el tema y generamos el contenido con IA', icon: <EditIcon /> },
  ]

  return (
    <div>
      <h3 className="text-base font-medium text-text">Elige el origen del curso</h3>
      <p className="text-sm text-text-secondary mt-1">Selecciona como quieres crear el contenido</p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-5">
        {sources.map((s) => (
          <Card
            key={s.key}
            variant="interactive"
            className={selected === s.key ? 'border-primary bg-primary-subtle' : ''}
            onClick={() => onSelect(s.key)}
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

function StepUpload({
  courseName,
  onNameChange,
}: {
  courseName: string
  onNameChange: (v: string) => void
}) {
  return (
    <div>
      <h3 className="text-base font-medium text-text">Contenido del curso</h3>
      <p className="text-sm text-text-secondary mt-1">Sube tus archivos y dale un nombre al curso</p>

      <div className="mt-5 space-y-4">
        <Input
          label="Nombre del curso"
          placeholder="Ej: Fundamentos de React"
          value={courseName}
          onChange={(e) => onNameChange(e.target.value)}
        />

        {/* Drop zone */}
        <div>
          <label className="block text-sm font-medium text-text mb-1">Archivos</label>
          <div className="border-2 border-dashed border-border rounded-lg py-10 flex flex-col items-center justify-center hover:border-primary/40 transition-colors cursor-pointer">
            <div className="text-text-muted mb-2">
              <UploadIcon />
            </div>
            <p className="text-sm text-text-secondary">
              Arrastra archivos aqui o <span className="text-primary font-medium">selecciona</span>
            </p>
            <p className="text-xs text-text-muted mt-1">PDF, PPTX, DOCX hasta 50MB</p>
          </div>
        </div>
      </div>
    </div>
  )
}

function StepGenerating({ progress }: { progress: number }) {
  const steps = [
    { label: 'Analizando contenido...', threshold: 0 },
    { label: 'Extrayendo conceptos clave...', threshold: 25 },
    { label: 'Generando modulos...', threshold: 50 },
    { label: 'Creando ejercicios...', threshold: 75 },
    { label: 'Finalizando...', threshold: 90 },
  ]

  const isComplete = progress >= 100

  return (
    <div className="text-center py-4">
      <h3 className="text-base font-medium text-text">
        {isComplete ? 'Curso generado' : 'Generando curso...'}
      </h3>
      <p className="text-sm text-text-secondary mt-1">
        {isComplete ? 'Redirigiendo a revision...' : 'Esto puede tomar unos momentos'}
      </p>

      <div className="max-w-md mx-auto mt-8">
        <ProgressBar value={progress} variant="primary" size="lg" showLabel />
      </div>

      <div className="max-w-xs mx-auto mt-6 space-y-2">
        {steps.map((step) => {
          const done = progress > step.threshold + 20
          const active = progress >= step.threshold && !done
          return (
            <div
              key={step.threshold}
              className={`flex items-center gap-2 text-sm ${
                done
                  ? 'text-accent'
                  : active
                  ? 'text-text font-medium'
                  : 'text-text-muted'
              }`}
            >
              {done ? (
                <span className="text-accent"><CheckIcon /></span>
              ) : active ? (
                <span className="inline-block w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              ) : (
                <span className="w-4 h-4 rounded-full bg-bg-muted" />
              )}
              {step.label}
            </div>
          )
        })}
      </div>
    </div>
  )
}

interface MockModule {
  title: string
  exercises: string[]
}

function StepReview() {
  const [modules] = useState<MockModule[]>([
    {
      title: 'Introduccion a JSX',
      exercises: ['Quiz: Sintaxis JSX', 'Ejercicio: Crear componente'],
    },
    {
      title: 'Componentes y Props',
      exercises: ['Quiz: Props vs State', 'Ejercicio: Componente reutilizable'],
    },
    {
      title: 'Estado y Efectos',
      exercises: ['Quiz: useState vs useEffect', 'Ejercicio: Contador interactivo', 'Ejercicio: Fetch de datos'],
    },
    {
      title: 'Patrones avanzados',
      exercises: ['Quiz: Render props', 'Ejercicio: Custom hook'],
    },
  ])

  return (
    <div>
      <h3 className="text-base font-medium text-text">Revisa el contenido generado</h3>
      <p className="text-sm text-text-secondary mt-1">
        {modules.length} modulos, {modules.reduce((acc, m) => acc + m.exercises.length, 0)} ejercicios generados
      </p>

      <div className="mt-5 space-y-3">
        {modules.map((mod, i) => (
          <Card key={i}>
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="truncate min-w-0">Modulo {i + 1}: {mod.title}</CardTitle>
              <Badge variant="accent" badgeStyle="plain">{mod.exercises.length} ejercicios</Badge>
            </div>
            <ul className="mt-2 space-y-1">
              {mod.exercises.map((ex, j) => (
                <li key={j} className="text-sm text-text-secondary flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-border shrink-0" />
                  {ex}
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>
    </div>
  )
}

function StepAssign() {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [deadline, setDeadline] = useState('')

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  return (
    <div>
      <h3 className="text-base font-medium text-text">Asignar a empleados</h3>
      <p className="text-sm text-text-secondary mt-1">Selecciona quienes tomaran este curso</p>

      <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-text mb-2">Empleados</label>
          <div className="border border-border rounded-lg max-h-64 overflow-y-auto">
            {employees.map((emp) => (
              <label
                key={emp.id}
                className="flex items-center gap-3 px-4 py-2.5 border-b border-border last:border-b-0 hover:bg-bg-subtle cursor-pointer transition-colors"
              >
                <input
                  type="checkbox"
                  checked={selected.has(emp.id)}
                  onChange={() => toggle(emp.id)}
                  className="accent-primary"
                />
                <div className="min-w-0">
                  <p className="text-sm text-text">{emp.name}</p>
                  <p className="text-xs text-text-muted">{emp.role}</p>
                </div>
              </label>
            ))}
          </div>
          <p className="text-xs text-text-muted mt-1">{selected.size} seleccionados</p>
        </div>

        <div>
          <Input
            label="Fecha limite"
            type="date"
            value={deadline}
            onChange={(e) => setDeadline(e.target.value)}
          />
          {selected.size > 0 && deadline && (
            <Card className="mt-4">
              <p className="text-sm text-text">Resumen de asignacion</p>
              <p className="text-xs text-text-muted mt-1">
                {selected.size} empleados recibiran el curso con fecha limite {deadline}
              </p>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}

// --- Main Component ---

const slideVariants = {
  enter: (dir: Direction) => ({
    x: dir > 0 ? 200 : -200,
    opacity: 0,
  }),
  center: {
    x: 0,
    opacity: 1,
  },
  exit: (dir: Direction) => ({
    x: dir > 0 ? -200 : 200,
    opacity: 0,
  }),
}

export function CreateCourse() {
  const [step, setStep] = useState(0)
  const [direction, setDirection] = useState<Direction>(1)
  const [source, setSource] = useState<SourceType>(null)
  const [courseName, setCourseName] = useState('')
  const [genProgress, setGenProgress] = useState(0)

  // Simulate generation progress
  useEffect(() => {
    if (step !== 2) return
    setGenProgress(0)
    const interval = setInterval(() => {
      setGenProgress((prev) => {
        if (prev >= 100) {
          clearInterval(interval)
          return 100
        }
        return prev + 2
      })
    }, 80)
    return () => clearInterval(interval)
  }, [step])

  // Auto-advance when generation completes
  useEffect(() => {
    if (step === 2 && genProgress >= 100) {
      const timeout = setTimeout(() => {
        setDirection(1)
        setStep(3)
      }, 600)
      return () => clearTimeout(timeout)
    }
  }, [step, genProgress])

  function canNext(): boolean {
    switch (step) {
      case 0: return source !== null
      case 1: return courseName.trim().length > 0
      case 2: return false // auto-advances
      case 3: return true
      case 4: return true
      default: return false
    }
  }

  function next() {
    if (step < 4 && canNext()) {
      setDirection(1)
      setStep(step + 1)
    }
  }

  function prev() {
    if (step > 0 && step !== 2) {
      setDirection(-1)
      setStep(step - 1)
    }
  }

  function renderStep() {
    switch (step) {
      case 0: return <StepSource selected={source} onSelect={setSource} />
      case 1: return <StepUpload courseName={courseName} onNameChange={setCourseName} />
      case 2: return <StepGenerating progress={genProgress} />
      case 3: return <StepReview />
      case 4: return <StepAssign />
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

      {/* Step content with transitions */}
      <div className="mt-6 overflow-hidden">
        <AnimatePresence mode="wait" custom={direction}>
          <motion.div
            key={step}
            custom={direction}
            variants={slideVariants}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ duration: 0.2, ease: 'easeOut' }}
          >
            {renderStep()}
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Navigation */}
      {step !== 2 && (
        <div className="flex items-center justify-between mt-8 pt-4 border-t border-border">
          <div>
            {step > 0 && (
              <Button variant="secondary" onClick={prev}>
                Anterior
              </Button>
            )}
          </div>
          <div>
            {step < 4 ? (
              <Button variant="primary" onClick={next} disabled={!canNext()}>
                Siguiente
              </Button>
            ) : (
              <Button variant="accent" onClick={() => setStep(0)}>
                Publicar curso
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
