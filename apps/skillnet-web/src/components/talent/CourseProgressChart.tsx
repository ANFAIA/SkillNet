import type { TalentCourseSummary } from '../../api/talent'
import { Card, CardTitle, EmptyState } from '../ui'

type CourseProgressChartProps = {
  courses: TalentCourseSummary[]
}

export function CourseProgressChart({ courses }: CourseProgressChartProps) {
  const visible = [...courses]
    .filter((course) => course.assigned_count > 0)
    .sort((a, b) => b.assigned_count - a.assigned_count || a.title.localeCompare(b.title))
    .slice(0, 5)

  return (
    <Card className="h-full">
      <CardTitle>Progreso por curso</CardTitle>
      <p className="mt-1 text-sm text-text-muted">Cursos con más personas asignadas.</p>
      {visible.length === 0 ? (
        <EmptyState title="Sin matrículas" description="Asigna un curso para empezar a comparar su progreso." />
      ) : (
        <div className="mt-5 space-y-4">
          {visible.map((course) => {
            const completion = course.assigned_count > 0 ? Math.round((course.completed_count / course.assigned_count) * 100) : 0
            const inProgress = course.assigned_count > 0 ? Math.round((course.in_progress_count / course.assigned_count) * 100) : 0
            return (
              <div key={course.course_id}>
                <div className="flex items-center justify-between gap-3">
                  <span className="truncate text-sm font-medium text-text">{course.title}</span>
                  <span className="shrink-0 text-xs text-text-muted tabular-nums">{course.completed_count}/{course.assigned_count}</span>
                </div>
                <svg viewBox="0 0 100 8" preserveAspectRatio="none" className="mt-2 h-2 w-full overflow-hidden rounded-full" role="img" aria-label={`${course.title}: ${completion}% completado, ${inProgress}% en curso`}>
                  <rect width="100" height="8" rx="4" className="fill-bg-muted" />
                  <rect width={completion} height="8" rx="4" className="fill-accent" />
                  <rect x={completion} width={inProgress} height="8" className="fill-warning" />
                </svg>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}
