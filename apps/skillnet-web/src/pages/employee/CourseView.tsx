import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Button, Card, ProgressBar, EmptyState, Skeleton, SkeletonText } from '../../components/ui'
import { LessonContent } from '../../components/courses/LessonContent'
import { NodeList } from '../../components/courses/NodeList'
import { ExerciseRenderer } from '../../components/exercises/ExerciseRenderer'
import { useCourse, useCompleteLesson, useCourseProgress } from '../../api/courses'
import { useCourseNodes } from '../../api/nodes'
import { useEnrollments, useCompleteEnrollment } from '../../api/enrollments'
import { useQueryClient } from '@tanstack/react-query'
import { slideVariants, staggerContainer, staggerItem, duration, ease, transition } from '../../lib/motion'
import type { CourseProgress, LessonProgress } from '../../types'

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

function LockIcon() {
  return (
    <svg
      width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      className="text-text-muted shrink-0"
    >
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg
      width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      className="text-accent shrink-0"
    >
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

function AlertOverlay({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, 2500)
    return () => clearTimeout(timer)
  }, [onDismiss])

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
      className="fixed inset-0 z-50 flex items-center justify-center"
      onClick={onDismiss}
    >
      <div className="absolute inset-0 bg-black/30" />
      <motion.div
        initial={{ opacity: 0, scale: 0.9, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ duration: 0.2, ease: [0.2, 0, 0, 1] }}
        className="relative bg-bg border border-border rounded-xl shadow-xl px-6 py-4 max-w-sm mx-4 text-center"
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="mx-auto mb-2 text-primary">
          <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
        <p className="text-sm text-text">{message}</p>
      </motion.div>
    </motion.div>
  )
}

export function CourseView() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: course, isLoading, error } = useCourse(id)
  const { data: enrollmentData } = useEnrollments(id ? { course_id: id } : undefined)
  const enrollment = enrollmentData?.items[0] ?? null
  const progress = enrollment?.progress ?? null
  const completeMutation = useCompleteEnrollment()
  const completeLessonMutation = useCompleteLesson()
  const { data: courseProgress } = useCourseProgress(id)
  const queryClient = useQueryClient()

  // --- v2 branch ---------------------------------------------------------------
  //
  // A dynamic course renders `NodeList`; anything else renders the v1 tree below,
  // untouched. The discriminator is `GET /courses/{id}/nodes`: if the course has a
  // validated dynamic schema the route returns the node list; otherwise it 404s, and
  // the component falls through to the v1 module/lesson tree.
  const nodesQuery = useCourseNodes(id)
  const dynamicNodes =
    nodesQuery.data?.delivery_mode === 'dynamic' ? nodesQuery.data : null
  // Wait for the answer before painting: showing the v1 tree and then replacing it
  // with the node map is precisely the layout jump §5.5 forbids.
  const dynamicPending = nodesQuery.isLoading

  const [expandedModules, setExpandedModules] = useState<Set<string>>(new Set())
  const [activeLessonId, setActiveLessonId] = useState<string>('')
  const [direction, setDirection] = useState<1 | -1>(1)
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  const dismissToast = useCallback(() => setToastMessage(null), [])

  // Build a lookup map for lesson progress
  const lessonProgressMap = new Map<string, LessonProgress>(
    courseProgress?.lessons?.map((lp) => [lp.lesson_id, lp]) ?? [],
  )

  // Initialize expansion / active lesson once when the course first loads.
  // Using a ref so that subsequent refetches of `course` do NOT reset the
  // active lesson (which would unmount exercise components and lose state).
  const initializedRef = useRef(false)
  useEffect(() => {
    if (!course || initializedRef.current) return
    initializedRef.current = true
    const firstModule = course.modules[0]
    setExpandedModules(new Set(firstModule ? [firstModule.id] : []))
    setActiveLessonId(firstModule?.lessons[0]?.id ?? '')
  }, [course])

  if (isLoading || dynamicPending) {
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

  if (dynamicNodes && id) {
    return (
      <div>
        <div className="mb-6 flex items-center gap-3 min-w-0">
          <span className="w-3 h-3 rounded-full shrink-0 bg-primary" />
          <h2 className="text-xl font-semibold text-text truncate">
            {course?.title ?? 'Curso'}
          </h2>
        </div>
        <NodeList courseId={id} data={dynamicNodes} />
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

  const allLessons = (course.modules ?? []).flatMap((m) => m.lessons ?? [])
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
    // Prevent navigation to locked lessons.
    const targetProgress = lessonProgressMap.get(lessonId)
    if (targetProgress?.locked) {
      setToastMessage('Completa la leccion anterior primero')
      return
    }
    // Record progress for the lesson the user is leaving.
    if (activeLessonId) markLessonComplete(activeLessonId)
    const targetIndex = allLessons.findIndex((l) => l.id === lessonId)
    setDirection(targetIndex >= currentIndex ? 1 : -1)
    setActiveLessonId(lessonId)
  }

  // Mark the current lesson as completed server-side (fire-and-forget).
  // The endpoint is idempotent and will only record progress if
  // exercises are satisfied.
  function markLessonComplete(lessonId: string) {
    completeLessonMutation.mutate(lessonId)
  }

  async function goToNext() {
    if (currentIndex < 0 || currentIndex >= allLessons.length - 1) return
    const currentLesson = allLessons[currentIndex]

    // Ensure we have fresh progress data — a recent "Corregir" submission may
    // have invalidated the query but the refetch might not have landed yet.
    await queryClient.refetchQueries({ queryKey: ['courses', id, 'progress'] })

    const freshProgress = queryClient.getQueryData<CourseProgress>(['courses', id, 'progress'])
    const freshMap = new Map<string, LessonProgress>(
      freshProgress?.lessons?.map((lp) => [lp.lesson_id, lp]) ?? [],
    )

    // Check exercises: use progress map if available, otherwise check if lesson has exercises at all.
    const currentProgress = freshMap.get(currentLesson.id)
    const hasExercises = currentProgress
      ? currentProgress.exercises_total > 0
      : (currentLesson.exercises ?? []).length > 0
    const exercisesDone = currentProgress
      ? currentProgress.exercises_passed >= currentProgress.exercises_total
      : false // If no progress data and has exercises, block
    if (hasExercises && !exercisesDone) {
      setToastMessage('Completa los ejercicios de esta leccion para continuar')
      return
    }
    // Record progress for the lesson the user is leaving.
    markLessonComplete(currentLesson.id)
    const nextLesson = allLessons[currentIndex + 1]
    setDirection(1)
    setActiveLessonId(nextLesson.id)
    const parentModule = course!.modules.find((m) => m.lessons.some((l) => l.id === nextLesson.id))
    if (parentModule) setExpandedModules((prev) => new Set(prev).add(parentModule.id))
  }

  return (
    <div>
      <AnimatePresence>
        {toastMessage && <AlertOverlay message={toastMessage} onDismiss={dismissToast} />}
      </AnimatePresence>
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2 min-w-0">
          <span className="w-3 h-3 rounded-full shrink-0 bg-primary" />
          <h2 className="text-xl font-semibold text-text truncate">{course.title}</h2>
        </div>
        {courseProgress ? (
          <ProgressBar value={courseProgress.progress_percent} variant="auto" size="lg" showLabel />
        ) : progress !== null ? (
          <ProgressBar value={Math.round(progress * 100)} variant="auto" size="lg" showLabel />
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
                        {(mod.lessons ?? []).map((lesson) => {
                          const lp = lessonProgressMap.get(lesson.id)
                          const isLocked = lp?.locked ?? false
                          const isCompleted = lp?.completed ?? false
                          return (
                            <motion.button
                              key={lesson.id}
                              type="button"
                              variants={staggerItem}
                              onClick={() => selectLesson(lesson.id)}
                              className={`w-full text-left px-6 py-2.5 text-sm transition-colors border-b border-border last:border-b-0 flex items-center gap-2 ${
                                isLocked
                                  ? 'text-text-muted cursor-not-allowed opacity-60'
                                  : activeLessonId === lesson.id
                                    ? 'bg-primary-subtle text-primary font-medium'
                                    : 'text-text-secondary hover:bg-bg-subtle'
                              }`}
                            >
                              {isCompleted && <CheckIcon />}
                              {isLocked && <LockIcon />}
                              <span className="truncate min-w-0">{lesson.title}</span>
                            </motion.button>
                          )
                        })}
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

                  {(activeLesson.exercises ?? [])
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
                    ) : courseProgress?.can_complete && enrollment?.status !== 'completed' ? (
                      <Button
                        variant="accent"
                        disabled={completeMutation.isPending}
                        onClick={async () => {
                          if (!enrollment) return
                          // Mark the last lesson complete before finalizing.
                          if (activeLesson) {
                            try { await completeLessonMutation.mutateAsync(activeLesson.id) } catch { /* already completed */ }
                          }
                          completeMutation.mutate(enrollment.id, {
                            onSuccess: () => navigate('/empleado/cursos'),
                          })
                        }}
                      >
                        {completeMutation.isPending ? 'Finalizando...' : 'Finalizar curso'}
                      </Button>
                    ) : enrollment?.status === 'completed' ? (
                      <Button variant="accent" disabled>
                        Curso completado
                      </Button>
                    ) : (
                      <Button disabled>
                        Completa todas las lecciones
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
