import { ProgressBar } from './ProgressBar'

export interface CourseItemProps {
  title: string
  subtitle: string
  progress: number
  color: string
  icon?: React.ReactNode
  onClick?: () => void
  className?: string
}

export function CourseItem({
  title,
  subtitle,
  progress,
  color,
  icon,
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
        </div>
        <p className="text-xs text-text-muted mt-0.5 ml-4">{subtitle}</p>
        <div className="flex items-center gap-2 mt-2 ml-4">
          <ProgressBar value={clamped} color={color} size="sm" className="flex-1" />
          <span className="text-xs font-medium text-text-secondary shrink-0">{clamped}%</span>
        </div>
      </div>
    </div>
  )
}
