import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Button, Card, ProgressBar, EmptyState } from '../../components/ui'
import { courses } from '../../data/mockData'
import type { Exercise } from '../../data/mockData'

function ChevronDown({ open }: { open: boolean }) {
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
      className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}

function ExerciseBlock({ exercise }: { exercise: Exercise }) {
  const [selected, setSelected] = useState<number | null>(null)
  const [submitted, setSubmitted] = useState(false)

  const isCorrect = selected === exercise.correctIndex

  return (
    <div className="mt-6 border-t border-border pt-6">
      <h4 className="text-sm font-medium text-text mb-3">Ejercicio</h4>
      <p className="text-sm text-text mb-4">{exercise.question}</p>

      <div className="space-y-2">
        {exercise.options.map((option, idx) => {
          let optionStyle = 'border-border'
          if (submitted && idx === exercise.correctIndex) {
            optionStyle = 'border-accent bg-accent-subtle'
          } else if (submitted && idx === selected && !isCorrect) {
            optionStyle = 'border-danger bg-danger/5'
          } else if (selected === idx && !submitted) {
            optionStyle = 'border-primary'
          }

          return (
            <label
              key={idx}
              className={`flex items-center gap-3 p-3 border rounded-lg cursor-pointer transition-colors ${optionStyle}`}
            >
              <input
                type="radio"
                name={exercise.id}
                checked={selected === idx}
                onChange={() => {
                  if (!submitted) setSelected(idx)
                }}
                disabled={submitted}
                className="accent-primary"
              />
              <span className="text-sm text-text">{option}</span>
            </label>
          )
        })}
      </div>

      {!submitted ? (
        <Button
          size="sm"
          className="mt-4"
          disabled={selected === null}
          onClick={() => setSubmitted(true)}
        >
          Comprobar
        </Button>
      ) : (
        <p className={`mt-4 text-sm font-medium ${isCorrect ? 'text-accent' : 'text-danger'}`}>
          {isCorrect ? 'Correcto' : 'Incorrecto. La respuesta correcta esta marcada en verde.'}
        </p>
      )}
    </div>
  )
}

export function CourseView() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const course = courses.find((c) => c.id === id)

  const [expandedModules, setExpandedModules] = useState<Set<string>>(() => {
    if (!course) return new Set<string>()
    return new Set([course.modules[0]?.id ?? ''])
  })
  const [activeLessonId, setActiveLessonId] = useState<string>(() => {
    if (!course) return ''
    return course.modules[0]?.lessons[0]?.id ?? ''
  })

  if (!course) {
    return (
      <EmptyState
        title="Curso no encontrado"
        action={{ label: 'Volver a cursos', onClick: () => navigate('/empleado/cursos') }}
      />
    )
  }

  const allLessons = course.modules.flatMap((m) => m.lessons)
  const currentIndex = allLessons.findIndex((l) => l.id === activeLessonId)
  const activeLesson = allLessons[currentIndex]

  function toggleModule(moduleId: string) {
    setExpandedModules((prev) => {
      const next = new Set(prev)
      if (next.has(moduleId)) {
        next.delete(moduleId)
      } else {
        next.add(moduleId)
      }
      return next
    })
  }

  function goToNext() {
    if (!course || currentIndex < 0 || currentIndex >= allLessons.length - 1) return
    const nextLesson = allLessons[currentIndex + 1]
    setActiveLessonId(nextLesson.id)
    // Expand the module containing the next lesson
    const parentModule = course.modules.find((m) =>
      m.lessons.some((l) => l.id === nextLesson.id),
    )
    if (parentModule) {
      setExpandedModules((prev) => new Set(prev).add(parentModule.id))
    }
  }

  return (
    <div>
      {/* Course header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2 min-w-0">
          <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: course.color }} />
          <h2 className="text-xl font-semibold text-text truncate">{course.title}</h2>
        </div>
        <ProgressBar value={course.progress} variant="auto" size="lg" showLabel />
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        {/* Sidebar - Module list */}
        <div className="w-full lg:w-72 lg:shrink-0">
          <Card className="p-0 overflow-hidden">
            {course.modules.map((mod) => {
              const isExpanded = expandedModules.has(mod.id)
              return (
                <div key={mod.id}>
                  <button
                    type="button"
                    onClick={() => toggleModule(mod.id)}
                    className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-text hover:bg-bg-subtle transition-colors border-b border-border"
                  >
                    <span className="text-left">{mod.title}</span>
                    <ChevronDown open={isExpanded} />
                  </button>
                  {isExpanded && (
                    <div>
                      {mod.lessons.map((lesson) => (
                        <button
                          key={lesson.id}
                          type="button"
                          onClick={() => setActiveLessonId(lesson.id)}
                          className={`w-full text-left px-6 py-2.5 text-sm transition-colors border-b border-border last:border-b-0 ${
                            activeLessonId === lesson.id
                              ? 'bg-primary-subtle text-primary font-medium'
                              : 'text-text-secondary hover:bg-bg-subtle'
                          }`}
                        >
                          {lesson.title}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </Card>
        </div>

        {/* Main content */}
        <div className="flex-1 min-w-0">
          <AnimatePresence mode="wait">
            {activeLesson && (
              <motion.div
                key={activeLesson.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
              >
                <Card>
                  <h3 className="text-base font-medium text-text mb-4">{activeLesson.title}</h3>
                  <div className="text-sm text-text-secondary leading-relaxed whitespace-pre-line">
                    {activeLesson.content}
                  </div>

                  {activeLesson.exercise && <ExerciseBlock exercise={activeLesson.exercise} />}

                  <div className="mt-6 flex justify-end">
                    {currentIndex < allLessons.length - 1 ? (
                      <Button onClick={goToNext}>Siguiente</Button>
                    ) : (
                      <Button variant="accent" onClick={() => navigate('/empleado/cursos')}>
                        Finalizar curso
                      </Button>
                    )}
                  </div>
                </Card>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}
