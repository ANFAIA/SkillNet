import { useNavigate } from 'react-router-dom'
import { Card, Badge, Button } from '../../components/ui'
import { adminCourses } from '../../data/adminMockData'
import type { AdminCourse } from '../../data/adminMockData'

const statusConfig: Record<AdminCourse['status'], { label: string; variant: 'accent' | 'warning' | 'primary' }> = {
  published: { label: 'Publicado', variant: 'accent' },
  draft: { label: 'Borrador', variant: 'warning' },
  archived: { label: 'Archivado', variant: 'primary' },
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

  const published = adminCourses.filter(c => c.status === 'published')
  const drafts = adminCourses.filter(c => c.status === 'draft')
  const archived = adminCourses.filter(c => c.status === 'archived')

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-text">Contenido</h2>
          <p className="text-sm text-text-secondary mt-1">{adminCourses.length} cursos en total</p>
        </div>
        <Button
          variant="primary"
          size="md"
          onClick={() => navigate('/admin/crear-curso')}
        >
          <span className="flex items-center gap-1.5">
            <PlusIcon />
            Crear nuevo
          </span>
        </Button>
      </div>

      {/* Stats row */}
      <div className="flex gap-4 mt-4">
        <div className="border border-border rounded-lg px-4 py-3 flex-1">
          <p className="text-xs text-text-muted">Publicados</p>
          <p className="text-lg font-semibold text-text">{published.length}</p>
        </div>
        <div className="border border-border rounded-lg px-4 py-3 flex-1">
          <p className="text-xs text-text-muted">Borradores</p>
          <p className="text-lg font-semibold text-text">{drafts.length}</p>
        </div>
        <div className="border border-border rounded-lg px-4 py-3 flex-1">
          <p className="text-xs text-text-muted">Archivados</p>
          <p className="text-lg font-semibold text-text">{archived.length}</p>
        </div>
      </div>

      {/* Course list */}
      <div className="mt-4 space-y-2">
        {adminCourses.map((course) => {
          const status = statusConfig[course.status]
          return (
            <Card key={course.id}>
              <div className="flex items-center gap-4">
                <div className="text-text-muted shrink-0">
                  <BookIcon />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-text truncate">{course.title}</span>
                    <Badge variant={status.variant} badgeStyle="plain">{status.label}</Badge>
                  </div>
                  <div className="flex items-center gap-4 mt-1 text-xs text-text-muted">
                    <span>{course.modules} modulos</span>
                    <span>{course.exercises} ejercicios</span>
                    {course.assignedCount > 0 && (
                      <span>{course.assignedCount} asignados</span>
                    )}
                    <span>Actualizado: {course.updatedAt}</span>
                  </div>
                </div>
              </div>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
