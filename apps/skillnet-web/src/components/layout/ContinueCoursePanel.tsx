import { Link } from 'react-router-dom'
import { useIntl } from 'react-intl'
import type { EnrollmentRead } from '../../types'

export function ContinueCoursePanel({
  enrollment,
  onNavigate,
}: {
  enrollment: EnrollmentRead
  onNavigate: () => void
}) {
  const intl = useIntl()
  const progress = Math.min(100, Math.max(0, Math.round((enrollment.progress ?? 0) * 100)))

  return (
    <Link
      to={`/empleado/curso/${enrollment.course_id}`}
      onClick={onNavigate}
      className="group mx-3 mb-3 block rounded-xl border border-border bg-surface p-3 text-text transition-colors hover:border-border-strong focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
    >
      <span className="flex items-center justify-between gap-3">
        <span className="grid size-7 place-items-center rounded-lg bg-bg-subtle text-text-muted">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M20 13c0 5-3.5 7.5-8 9-4.5-1.5-8-4-8-9V5l8-3 8 3z" />
            <path d="m9 12 2 2 4-4" />
          </svg>
        </span>
        <span className="text-xs tabular-nums text-text-muted">{progress}%</span>
      </span>

      <span className="mt-3 block truncate text-xs font-semibold">
        {enrollment.course_title}
      </span>

      <span className="mt-2 flex items-center justify-between gap-2 text-[11px] text-text-muted">
        <span>{intl.formatMessage({ id: 'nav.continueCourse' })}</span>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="transition-transform group-hover:translate-x-0.5">
          <path d="M5 12h14" />
          <path d="m13 6 6 6-6 6" />
        </svg>
      </span>

      <progress
        className="sidebar-course-progress mt-3 block h-1 w-full overflow-hidden rounded-full"
        max={100}
        value={progress}
        aria-label={intl.formatMessage(
          { id: 'nav.courseProgress' },
          { progress },
        )}
      />
    </Link>
  )
}
