import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useIntl } from 'react-intl'
import { motion, AnimatePresence } from 'framer-motion'
import { Button, Badge, Card, EmptyState, Input, Skeleton, SkeletonText } from '../../components/ui'
import { LessonContent } from '../../components/courses/LessonContent'
import { ExerciseRenderer } from '../../components/exercises/ExerciseRenderer'
import { useCourse, useUpdateCourse, usePublishCourse, useArchiveCourse } from '../../api/courses'
import { useDocument } from '../../api/documents'
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

function useStatusConfig() {
  const intl = useIntl()
  return {
    published: { label: intl.formatMessage({ id: 'status.published' }), variant: 'accent' as const },
    draft: { label: intl.formatMessage({ id: 'status.draft' }), variant: 'warning' as const },
    archived: { label: intl.formatMessage({ id: 'status.archived' }), variant: 'primary' as const },
  }
}

export function CoursePreview() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const intl = useIntl()
  const statusConfig = useStatusConfig()
  const { data: course, isLoading, error } = useCourse(id)
  // Where the content came from. A course built on a source the model wrote is not the
  // same claim as one built on the company's own material, and the creator has to be
  // able to see which one they are looking at without going digging.
  const { data: sourceDoc } = useDocument(course?.source_document_id)

  const updateCourse = useUpdateCourse()
  const publishCourse = usePublishCourse()
  const archiveCourse = useArchiveCourse()

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
        title={intl.formatMessage({ id: 'preview.notFound' })}
        description={intl.formatMessage({ id: 'preview.notFoundDesc' })}
        action={{ label: intl.formatMessage({ id: 'preview.backToContent' }), onClick: () => navigate('/admin/contenido') }}
      />
    )
  }

  const status = statusConfig[course.status as keyof typeof statusConfig] ?? { label: course.status, variant: 'primary' as const }

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
        {editing ? (
          <div className="space-y-3">
            <Input
              label={intl.formatMessage({ id: 'preview.titleLabel' })}
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
            />
            <div className="space-y-1">
              <label className="block text-sm font-medium text-text">{intl.formatMessage({ id: 'preview.descLabel' })}</label>
              <textarea
                className="w-full px-3 py-2 text-sm text-text border border-border rounded-lg bg-bg placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors duration-150 min-h-[80px] resize-y"
                value={editDescription}
                onChange={(e) => setEditDescription(e.target.value)}
              />
            </div>
            <Input
              label={intl.formatMessage({ id: 'preview.outcomeLabel' })}
              value={editOutcome}
              onChange={(e) => setEditOutcome(e.target.value)}
            />
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                onClick={saveEditing}
                disabled={updateCourse.isPending || !editTitle.trim()}
              >
                {updateCourse.isPending ? intl.formatMessage({ id: 'preview.saving' }) : intl.formatMessage({ id: 'preview.save' })}
              </Button>
              <Button variant="ghost" size="sm" onClick={cancelEditing} disabled={updateCourse.isPending}>
                {intl.formatMessage({ id: 'preview.cancel' })}
              </Button>
              {updateCourse.isError && (
                <span className="text-xs text-danger">{intl.formatMessage({ id: 'preview.saveError' })}</span>
              )}
            </div>
          </div>
        ) : (
          <>
            <div className="shrink-0 flex items-baseline gap-1.5 mb-2">
              <h2
                className="text-xl font-semibold transition-colors duration-200 text-text-muted cursor-pointer hover:text-text"
                onClick={() => navigate('/admin/contenido')}
                role="button"
              >
                {intl.formatMessage({ id: 'content.title' })}
              </h2>
              <motion.span
                key="breadcrumb-course"
                className="text-xl font-semibold text-text"
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0, transition: { duration: duration.normal, ease: ease.base } }}
              >
                / {course.title}
              </motion.span>
              <Badge variant={status.variant} badgeStyle="plain" className="shrink-0 ml-1.5">
                {status.label}
              </Badge>
            </div>
            {course.description && (
              <p className="text-sm text-text-secondary mb-1">{course.description}</p>
            )}
            {course.outcome && (
              <p className="text-sm text-text-muted mb-1">{intl.formatMessage({ id: 'preview.objective' }, { outcome: course.outcome })}</p>
            )}
            <p className="text-sm text-text-secondary">
              {intl.formatMessage({ id: 'preview.modulesLessons' }, { modules: course.modules.length, lessons: allLessons.length })}
            </p>
            {sourceDoc && (
              <p className="text-sm text-text-secondary mt-1 flex items-center gap-2 flex-wrap">
                <span className="text-text-muted">{intl.formatMessage({ id: 'preview.source' })}</span>
                <span className="truncate">{sourceDoc.title}</span>
                {sourceDoc.origin === 'generated' && (
                  <Badge variant="warning" badgeStyle="plain" className="shrink-0">
                    {intl.formatMessage({ id: 'preview.aiGenerated' })}
                  </Badge>
                )}
              </p>
            )}
            <div className="flex items-center gap-2 mt-3">
              <Button variant="secondary" size="sm" onClick={startEditing}>
                {intl.formatMessage({ id: 'preview.edit' })}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate(`/admin/curso/${id}/esquema`)}
              >
                {intl.formatMessage({ id: 'preview.schema' })}
              </Button>
              {course.status === 'draft' && (
                <Button
                  variant="accent"
                  size="sm"
                  onClick={() => id && publishCourse.mutate(id)}
                  disabled={publishCourse.isPending}
                >
                  {publishCourse.isPending ? intl.formatMessage({ id: 'preview.publishing' }) : intl.formatMessage({ id: 'preview.publish' })}
                </Button>
              )}
              {course.status === 'published' && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => id && archiveCourse.mutate(id)}
                  disabled={archiveCourse.isPending}
                >
                  {archiveCourse.isPending ? intl.formatMessage({ id: 'preview.archiving' }) : intl.formatMessage({ id: 'preview.archive' })}
                </Button>
              )}
              {(publishCourse.isError || archiveCourse.isError) && (
                <span className="text-xs text-danger">{intl.formatMessage({ id: 'preview.statusError' })}</span>
              )}
            </div>
          </>
        )}
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        <div className="w-full lg:w-72 lg:shrink-0">
          <Card className="p-0 overflow-hidden">
            {course.modules.length === 0 ? (
              <div className="p-4 text-sm text-text-muted">{intl.formatMessage({ id: 'preview.noContent' })}</div>
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
                        <h4 className="text-sm font-medium text-text mb-3">{intl.formatMessage({ id: 'preview.exerciseNum' }, { num: i + 1 })}</h4>
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
                        {intl.formatMessage({ id: 'preview.previous' })}
                      </Button>
                    ) : <div />}
                    {currentIndex < allLessons.length - 1 ? (
                      <Button
                        onClick={() => {
                          setDirection(1)
                          setActiveLessonId(allLessons[currentIndex + 1].id)
                        }}
                      >
                        {intl.formatMessage({ id: 'preview.next' })}
                      </Button>
                    ) : (
                      <Button variant="ghost" onClick={() => navigate('/admin/contenido')}>
                        {intl.formatMessage({ id: 'preview.backToContent' })}
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
