import { ProgressBar } from './ProgressBar'

export interface CourseItemProps {
  title: string
  subtitle: string
  progress: number
  color: string
  icon?: React.ReactNode
  /** Optional marker rendered after the title — a `Badge`, not a second line of copy. */
  badge?: React.ReactNode
  onClick?: () => void
  className?: string
}

export function CourseItem({
  title,
  subtitle,
  progress,
  color,
  icon,
  badge,
  onClick,
  className = '',
}: CourseItemProps) {
  const clamped = Math.max(0, Math.min(100, progress))

  return (
    <div
      className={`flex items-start gap-3 py-3 border-b border-border last:border-b-0 ${onClick ? 'cursor-pointer hover:bg-bg-subtle transition-colors' : ''} ${className}`}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick() } } : undefined}
    >
      {icon && (
        <div className="shrink-0 mt-0.5 text-text-muted">
          {icon}
        </div>
      )}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span
            className="shrink-0 w-2 h-2 rounded-full"
            style={{ backgroundColor: color }}
          />
          <span className="text-sm font-medium text-text truncate">{title}</span>
          {badge && <span className="shrink-0">{badge}</span>}
        </div>
        <p className="text-xs text-text-muted mt-0.5 ml-4">{subtitle}</p>
        <div className="flex items-center gap-2 mt-2 ml-4">
          {/*
            `color` identifies the course (that is the dot above); it must not also paint
            the bar. Passing it here made the bar the same colour at every value — a
            course at 100% in the "Completados" tab looked exactly like one at 5% — because
            a `color` overrides the variant inside `ProgressBar`. The bar reads *progress*,
            so it uses `auto` like every other learner-facing course bar: green from 80%.
          */}
          <ProgressBar value={clamped} variant="auto" size="sm" className="flex-1" />
          <span className="text-xs font-medium text-text-secondary shrink-0">{Math.round(clamped)}%</span>
        </div>
      </div>
    </div>
  )
}
