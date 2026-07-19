import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Button, Card, ProgressBar, EmptyState, Skeleton, SkeletonText } from '../../components/ui'
import { LessonContent } from '../../components/courses/LessonContent'
import { ExerciseRenderer } from '../../components/exercises/ExerciseRenderer'
import { useCourse } from '../../api/courses'
import { useEnrollments } from '../../api/enrollments'
import { slideVariants, staggerContainer, staggerItem, duration, ease, transition } from '../../lib/motion'

const lessonSlide = slideVariants(48)

function ChevronDown({ open }: { open: boolean }) {
  return (
    <svg
      width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}

export function CourseView() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: course, isLoading, error } = useCourse(id)
  const { data: enrollmentData } = useEnrollments(id ? { course_id: id } : undefined)
  const progress = enrollmentData?.items[0]?.progress ?? null

  const [expandedModules, setExpandedModules] = useState<Set<string>>(new Set())
  const [activeLessonId, setActiveLessonId] = useState<string>('')
  const [direction, setDirection] = useState<1 | -1>(1)

  // Initialize expansion / active lesson once the course loads.
  useEffect(() => {
    if (!course) return
    const firstModule = course.modules[0]
    setExpandedModules(new Set(firstModule ? [firstModule.id] : []))
    setActiveLessonId(firstModule?.lessons[0]?.id ?? '')
  }, [course])

  if (isLoading) {
    return (
      <div>
        <Skeleton className="h-6 w-1/3 mb-6" />
        <div className="flex flex-col lg:flex-row gap-6">
          <div className="w-full lg:w-72 lg:shrink-0">
            <Card><SkeletonText lines={5} /></Card>
          </div>
          <div className="flex-1 min-w-0">
            <Card><SkeletonText lines={8} /></Card>
          </div>
        </div>
      </div>
    )
  }

  if (error || !course) {
    return (
      <EmptyState
        title="Curso no encontrado"
        description="No se pudo cargar este curso"
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
      if (next.has(moduleId)) next.delete(moduleId)
      else next.add(moduleId)
      return next
    })
  }

  // Switch lesson with a directional transition — forward slides in from the
  // right, going back slides in from the left.
  function selectLesson(lessonId: string) {
    if (lessonId === activeLessonId) return
    const targetIndex = allLessons.findIndex((l) => l.id === lessonId)
    setDirection(targetIndex >= currentIndex ? 1 : -1)
    setActiveLessonId(lessonId)
  }

  function goToNext() {
    if (currentIndex < 0 || currentIndex >= allLessons.length - 1) return
    const nextLesson = allLessons[currentIndex + 1]
    setDirection(1)
    setActiveLessonId(nextLesson.id)
    const parentModule = course!.modules.find((m) => m.lessons.some((l) => l.id === nextLesson.id))
    if (parentModule) setExpandedModules((prev) => new Set(prev).add(parentModule.id))
  }

  return (
    <div>
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2 min-w-0">
          <span className="w-3 h-3 rounded-full shrink-0 bg-primary" />
          <h2 className="text-xl font-semibold text-text truncate">{course.title}</h2>
        </div>
        {progress !== null ? (
          <ProgressBar value={progress} variant="auto" size="lg" showLabel />
        ) : (
          <p className="text-sm text-text-secondary">
            {course.modules.length} modulos · {allLessons.length} lecciones
          </p>
        )}
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        <div className="w-full lg:w-72 lg:shrink-0">
          <Card className="p-0 overflow-hidden">
            {course.modules.length === 0 ? (
              <div className="p-4 text-sm text-text-muted">Este curso aun no tiene contenido.</div>
            ) : (
              course.modules.map((mod) => {
                const isExpanded = expandedModules.has(mod.id)
                return (
                  <div key={mod.id}>
                    <button
                      type="button"
                      onClick={() => toggleModule(mod.id)}
                      className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-text hover:bg-bg-subtle transition-colors border-b border-border"
                    >
                      <span className="text-left truncate min-w-0">{mod.title}</span>
                      <ChevronDown open={isExpanded} />
                    </button>
                    {isExpanded && (
                      <motion.div initial="hidden" animate="visible" variants={staggerContainer}>
                        {mod.lessons.map((lesson) => (
                          <motion.button
                            key={lesson.id}
                            type="button"
                            variants={staggerItem}
                            onClick={() => selectLesson(lesson.id)}
                            className={`w-full text-left px-6 py-2.5 text-sm transition-colors border-b border-border last:border-b-0 ${
                              activeLessonId === lesson.id
                                ? 'bg-primary-subtle text-primary font-medium'
                                : 'text-text-secondary hover:bg-bg-subtle'
                            }`}
                          >
                            {lesson.title}
                          </motion.button>
                        ))}
                      </motion.div>
                    )}
                  </div>
                )
              })
            )}
          </Card>
        </div>

        <div className="flex-1 min-w-0">
          <AnimatePresence mode="wait" custom={direction} initial={false}>
            {activeLesson && (
              <motion.div
                key={activeLesson.id}
                custom={direction}
                variants={lessonSlide}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{
                  x: direction > 0 ? transition.pushIn : transition.pushOut,
                  opacity: { duration: duration.normal, ease: ease.base },
                  filter: { duration: duration.normal, ease: ease.base },
                }}
              >
                <Card>
                  <h3 className="text-base font-medium text-text mb-4">{activeLesson.title}</h3>

                  <LessonContent markdown={activeLesson.content} />

                  {activeLesson.exercises
                    .slice()
                    .sort((a, b) => a.position - b.position)
                    .map((exercise, i) => (
                      <div key={exercise.id} className="mt-6 border-t border-border pt-6">
                        <h4 className="text-sm font-medium text-text mb-3">Ejercicio {i + 1}</h4>
                        <ExerciseRenderer exercise={exercise} />
                      </div>
                    ))}

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
