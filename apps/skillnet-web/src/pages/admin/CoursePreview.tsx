import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Button, Badge, Card, EmptyState, Input, Skeleton, SkeletonText } from '../../components/ui'
import { LessonContent } from '../../components/courses/LessonContent'
import { ExerciseRenderer } from '../../components/exercises/ExerciseRenderer'
import { useCourse, useUpdateCourse, usePublishCourse, useArchiveCourse } from '../../api/courses'
import { useDynamicCoursesMode } from '../../api/health'
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

const statusConfig: Record<string, { label: string; variant: 'accent' | 'warning' | 'primary' }> = {
  published: { label: 'Publicado', variant: 'accent' },
  draft: { label: 'Borrador', variant: 'warning' },
  archived: { label: 'Archivado', variant: 'primary' },
}

export function CoursePreview() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { data: course, isLoading, error } = useCourse(id)

  const updateCourse = useUpdateCourse()
  const publishCourse = usePublishCourse()
  const archiveCourse = useArchiveCourse()

  /**
   * Same gate as the course list (§11.1): the global flag, never `delivery_mode`. A
   * course whose schema is still `draft` or `proposed` reads `'static'`, and that is
   * exactly the course whose schema someone needs to open.
   */
  const { mode: dynamicMode } = useDynamicCoursesMode()
  const schemaAvailable = dynamicMode === 'shadow' || dynamicMode === 'on'

  const [expandedModules, setExpandedModules] = useState<Set<string>>(new Set())
  const [activeLessonId, setActiveLessonId] = useState<string>('')
  const [direction, setDirection] = useState<1 | -1>(1)

  const [editing, setEditing] = useState(false)
  const [editTitle, setEditTitle] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [editOutcome, setEditOutcome] = useState('')

  const initializedRef = useRef(false)
  useEffect(() => {
    if (!course || initializedRef.current) return
    initializedRef.current = true
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
        action={{ label: 'Volver a contenido', onClick: () => navigate('/admin/contenido') }}
      />
    )
  }

  const status = statusConfig[course.status] ?? { label: course.status, variant: 'primary' as const }

  function startEditing() {
    if (!course) return
    setEditTitle(course.title)
    setEditDescription(course.description ?? '')
    setEditOutcome(course.outcome ?? '')
    setEditing(true)
  }

  function cancelEditing() {
    setEditing(false)
  }

  function saveEditing() {
    if (!id) return
    updateCourse.mutate(
      { id, payload: { title: editTitle, description: editDescription, outcome: editOutcome } },
      { onSuccess: () => setEditing(false) },
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

  function selectLesson(lessonId: string) {
    if (lessonId === activeLessonId) return
    const targetIndex = allLessons.findIndex((l) => l.id === lessonId)
    setDirection(targetIndex >= currentIndex ? 1 : -1)
    setActiveLessonId(lessonId)
  }

  return (
    <div>
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/admin/contenido')}
          >
            ← Contenido
          </Button>
        </div>

        {editing ? (
          <div className="space-y-3">
            <Input
              label="Titulo"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
            />
            <div className="space-y-1">
              <label className="block text-sm font-medium text-text">Descripcion</label>
              <textarea
                className="w-full px-3 py-2 text-sm text-text border border-border rounded-lg bg-bg placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors duration-150 min-h-[80px] resize-y"
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
              />
            </div>
            <Input
              label="Objetivo de aprendizaje"
              value={editOutcome}
              onChange={(e) => setEditOutcome(e.target.value)}
            />
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                onClick={saveEditing}
                disabled={updateCourse.isPending || !editTitle.trim()}
              >
                {updateCourse.isPending ? 'Guardando...' : 'Guardar'}
              </Button>
              <Button variant="ghost" size="sm" onClick={cancelEditing} disabled={updateCourse.isPending}>
                Cancelar
              </Button>
              {updateCourse.isError && (
                <span className="text-xs text-danger">Error al guardar</span>
              )}
            </div>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-3 mb-2 min-w-0">
              <span className="w-3 h-3 rounded-full shrink-0 bg-primary" />
              <h2 className="text-xl font-semibold text-text truncate">{course.title}</h2>
              <Badge variant={status.variant} badgeStyle="plain" className="shrink-0">
                {status.label}
              </Badge>
            </div>
            {course.description && (
              <p className="text-sm text-text-secondary mb-1">{course.description}</p>
            )}
            {course.outcome && (
              <p className="text-sm text-text-muted mb-1">Objetivo: {course.outcome}</p>
            )}
            <p className="text-sm text-text-secondary">
              {course.modules.length} modulos · {allLessons.length} lecciones
            </p>
            <div className="flex items-center gap-2 mt-3">
              <Button variant="secondary" size="sm" onClick={startEditing}>
                Editar
              </Button>
              {schemaAvailable && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => navigate(`/admin/curso/${id}/esquema`)}
                >
                  Esquema
                </Button>
              )}
              {course.status === 'draft' && (
                <Button
                  variant="accent"
                  size="sm"
                  onClick={() => id && publishCourse.mutate(id)}
                  disabled={publishCourse.isPending}
                >
                  {publishCourse.isPending ? 'Publicando...' : 'Publicar'}
                </Button>
              )}
              {course.status === 'published' && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => id && archiveCourse.mutate(id)}
                  disabled={archiveCourse.isPending}
                >
                  {archiveCourse.isPending ? 'Archivando...' : 'Archivar'}
                </Button>
              )}
              {(publishCourse.isError || archiveCourse.isError) && (
                <span className="text-xs text-danger">Error al cambiar estado</span>
              )}
            </div>
          </>
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
                        {(mod.lessons ?? []).map((lesson) => (
                          <motion.button
                            key={lesson.id}
                            type="button"
                            variants={staggerItem}
                            onClick={() => selectLesson(lesson.id)}
                            className={`w-full text-left px-6 py-2.5 text-sm transition-colors border-b border-border last:border-b-0 flex items-center gap-2 ${
                              activeLessonId === lesson.id
                                ? 'bg-primary-subtle text-primary font-medium'
                                : 'text-text-secondary hover:bg-bg-subtle'
                            }`}
                          >
                            <span className="truncate min-w-0">{lesson.title}</span>
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

                  {(activeLesson.exercises ?? [])
                    .slice()
                    .sort((a, b) => a.position - b.position)
                    .map((exercise, i) => (
                      <div key={exercise.id} className="mt-6 border-t border-border pt-6">
                        <h4 className="text-sm font-medium text-text mb-3">Ejercicio {i + 1}</h4>
                        <ExerciseRenderer exercise={exercise} />
                      </div>
                    ))}

                  <div className="mt-6 flex justify-between">
                    {currentIndex > 0 ? (
                      <Button
                        variant="ghost"
                        onClick={() => {
                          setDirection(-1)
                          setActiveLessonId(allLessons[currentIndex - 1].id)
                        }}
                      >
                        ← Anterior
                      </Button>
                    ) : <div />}
                    {currentIndex < allLessons.length - 1 ? (
                      <Button
                        onClick={() => {
                          setDirection(1)
                          setActiveLessonId(allLessons[currentIndex + 1].id)
                        }}
                      >
                        Siguiente →
                      </Button>
                    ) : (
                      <Button variant="ghost" onClick={() => navigate('/admin/contenido')}>
                        Volver a contenido
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
