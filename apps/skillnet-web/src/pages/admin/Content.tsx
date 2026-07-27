import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Card, Badge, Button, EmptyState, SkeletonCard } from '../../components/ui'
import { useCourses } from '../../api/courses'
import { useDynamicCoursesMode } from '../../api/health'
import { ApiError } from '../../api/client'
import { staggerContainer, staggerItem } from '../../lib/motion'
import type { CourseStatus } from '../../types'

const statusConfig: Record<string, { label: string; variant: 'accent' | 'warning' | 'primary' }> = {
  published: { label: 'Publicado', variant: 'accent' },
  draft: { label: 'Borrador', variant: 'warning' },
  archived: { label: 'Archivado', variant: 'primary' },
}

function statusOf(status: CourseStatus) {
  return statusConfig[status] ?? { label: status, variant: 'primary' as const }
}

function BookIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
    </svg>
  )
}

function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

export function Content() {
  const navigate = useNavigate()
  const { data, isLoading, error } = useCourses()

  /**
   * The per-course door to the schema screen (§11.1). Gated on the global flag, **not**
   * on `delivery_mode`: that field only reads `'dynamic'` once a schema is validated, and
   * a `draft` or `proposed` schema is precisely what this link exists to reach.
   */
  const { mode: dynamicMode } = useDynamicCoursesMode()
  const schemaAvailable = dynamicMode === 'shadow' || dynamicMode === 'on'

  const courses = data?.items ?? []
  const published = courses.filter((c) => c.status === 'published')
  const drafts = courses.filter((c) => c.status === 'draft')
  const archived = courses.filter((c) => c.status === 'archived')

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-text">Contenido</h2>
          <p className="text-sm text-text-secondary mt-1">{courses.length} cursos en total</p>
        </div>
        <Button variant="primary" size="md" onClick={() => navigate('/admin/crear-curso')}>
          <span className="flex items-center gap-1.5">
            <PlusIcon />
            Crear nuevo
          </span>
        </Button>
      </div>

      <div className="grid grid-cols-3 gap-2 sm:gap-4 mt-4">
        <div className="border border-border rounded-lg px-3 sm:px-4 py-3">
          <p className="text-xs text-text-muted">Publicados</p>
          <p className="text-lg font-semibold text-text">{published.length}</p>
        </div>
        <div className="border border-border rounded-lg px-3 sm:px-4 py-3">
          <p className="text-xs text-text-muted">Borradores</p>
          <p className="text-lg font-semibold text-text">{drafts.length}</p>
        </div>
        <div className="border border-border rounded-lg px-3 sm:px-4 py-3">
          <p className="text-xs text-text-muted">Archivados</p>
          <p className="text-lg font-semibold text-text">{archived.length}</p>
        </div>
      </div>

      <div className="mt-4 space-y-2">
        {isLoading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : error ? (
          <Card>
            <EmptyState
              title="No se pudieron cargar los cursos"
              description={error instanceof ApiError ? error.body.detail : 'Intentalo de nuevo'}
            />
          </Card>
        ) : courses.length === 0 ? (
          <Card>
            <EmptyState
              title="Aun no hay cursos"
              description="Crea tu primer curso a partir de un documento"
              action={{ label: 'Crear curso', onClick: () => navigate('/admin/crear-curso') }}
            />
          </Card>
        ) : (
          <motion.div className="space-y-2" initial="hidden" animate="visible" variants={staggerContainer}>
          {courses.map((course) => {
            const status = statusOf(course.status)
            return (
              <Card key={course.id} variants={staggerItem}>
                <div className="flex items-center gap-4 min-w-0">
                  <div className="text-text-muted shrink-0">
                    <BookIcon />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-sm font-medium text-text truncate min-w-0">{course.title}</span>
                      <Badge variant={status.variant} badgeStyle="plain" className="shrink-0">
                        {status.label}
                      </Badge>
                    </div>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-0.5 mt-1 text-xs text-text-muted">
                      <span>{course.module_count} modulos</span>
                      {course.outcome && <span className="truncate max-w-xs">{course.outcome}</span>}
                      <span>Creado: {new Date(course.created_at).toLocaleDateString()}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {course.module_count > 0 && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => navigate(`/admin/curso/${course.id}`)}
                      >
                        Ver curso
                      </Button>
                    )}
                    {schemaAvailable && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => navigate(`/admin/curso/${course.id}/esquema`)}
                      >
                        Esquema
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            )
          })}
          </motion.div>
        )}
      </div>
    </div>
  )
}
