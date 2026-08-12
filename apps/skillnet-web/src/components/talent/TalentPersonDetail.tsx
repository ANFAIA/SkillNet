import { useTalentPerson } from '../../api/talent'
import type { EnrollmentStatus } from '../../types'
import { formatSkillName } from '../../lib/formatSkillName'
import { EmptyState, ProgressBar, Skeleton, SkeletonRow } from '../ui'

type TalentPersonDetailProps = {
  userId: string
  onClose: () => void
}

const statusOrder: EnrollmentStatus[] = ['in_progress', 'assigned', 'completed']

function statusLabel(status: EnrollmentStatus): string {
  if (status === 'completed') return 'Completados'
  if (status === 'in_progress') return 'En curso'
  return 'Sin iniciar'
}

function progressPercent(value: number | null): number {
  return Math.round(Math.min(1, Math.max(0, value ?? 0)) * 100)
}

function formatDate(value: string | null): string {
  if (!value) return ''
  return new Intl.DateTimeFormat('es', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(value))
}

export function TalentPersonDetail({ userId, onClose }: TalentPersonDetailProps) {
  const detail = useTalentPerson(userId)

  return (
    <aside className="min-w-0 rounded-lg border border-border bg-surface p-5" aria-label="Detalle de talento">
      {detail.isLoading ? (
        <div><Skeleton className="h-5 w-1/2" /><Skeleton className="mt-2 h-3 w-2/3" /><div className="mt-6 space-y-3"><SkeletonRow /><SkeletonRow /></div></div>
      ) : detail.error || !detail.data ? (
        <EmptyState title="No se pudo cargar el registro" description="La lista de personas sigue disponible. Puedes volver a intentarlo." action={{ label: 'Reintentar', onClick: () => void detail.refetch() }} />
      ) : (
        <>
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0"><h2 className="truncate text-lg font-semibold text-text">{detail.data.full_name}</h2><p className="truncate text-sm text-text-muted">{detail.data.email}</p></div>
            <button type="button" onClick={onClose} className="text-sm text-text-muted hover:text-text">Cerrar</button>
          </div>

          <section className="mt-6">
            <h3 className="text-sm font-medium text-text">Cursos</h3>
            {detail.data.courses.length === 0 ? <p className="mt-2 text-sm text-text-muted">Todavía no tiene cursos asignados.</p> : (
              <div className="mt-3 space-y-5">
                {statusOrder.map((status) => {
                  const courses = detail.data.courses.filter((course) => course.status === status)
                  if (courses.length === 0) return null
                  return (
                    <div key={status}>
                      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-muted">{statusLabel(status)} · {courses.length}</p>
                      <div className="divide-y divide-border rounded-lg border border-border px-3">
                        {courses.map((course) => (
                          <div key={course.course_id} className="py-3">
                            <div className="flex items-center justify-between gap-3"><p className="min-w-0 truncate text-sm font-medium text-text">{course.title}</p><span className="shrink-0 text-xs text-text-muted tabular-nums">{progressPercent(course.progress)}%</span></div>
                            <ProgressBar value={progressPercent(course.progress)} size="sm" className="mt-2" />
                          </div>
                        ))}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </section>

          <section className="mt-6 border-t border-border pt-5">
            <h3 className="text-sm font-medium text-text">Habilidades obtenidas</h3>
            {detail.data.skills.length === 0 ? <p className="mt-2 text-sm text-text-muted">Todavía no tiene habilidades registradas.</p> : (
              <ul className="mt-3 flex flex-wrap gap-2">
                {detail.data.skills.map((skill) => (
                  <li key={skill.id} className="max-w-full rounded-md border border-border bg-bg-subtle px-3 py-2">
                    <p className="text-sm font-medium text-text">{formatSkillName(skill.skill_name)}</p>
                    <p className="mt-0.5 text-xs text-text-muted">
                      {skill.source_courses.length > 0 ? skill.source_courses.map((course) => course.title).join(', ') : skill.source}
                      {skill.last_assessed_at ? ` · ${formatDate(skill.last_assessed_at)}` : ''}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </aside>
  )
}
