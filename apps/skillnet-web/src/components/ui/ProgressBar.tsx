type ProgressVariant = 'primary' | 'accent' | 'auto'
type ProgressSize = 'sm' | 'md' | 'lg'

export interface ProgressBarProps {
  value: number  // 0-100
  variant?: ProgressVariant
  size?: ProgressSize
  color?: string
  showLabel?: boolean
  className?: string
}

const sizeClasses: Record<ProgressSize, string> = {
  sm: 'h-1',
  md: 'h-1.5',
  lg: 'h-2',
}

function getAutoColor(value: number): string {
  if (value >= 80) return 'bg-accent'
  if (value >= 40) return 'bg-primary'
  return 'bg-warning'
}

const variantClasses: Record<Exclude<ProgressVariant, 'auto'>, string> = {
  primary: 'bg-primary',
  accent: 'bg-accent',
}

export function ProgressBar({
  value,
  variant = 'primary',
  size = 'md',
  color,
  showLabel = false,
  className = '',
}: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, value))
  const barColor = color ? undefined : (variant === 'auto' ? getAutoColor(clamped) : variantClasses[variant])

  return (
    <div className={`max-w-full ${className}`}>
      {showLabel && (
        <div className="flex justify-between items-center mb-1">
          <span className="text-xs text-text-secondary">{Math.round(clamped)}%</span>
        </div>
      )}
      <div className={`bg-bg-muted rounded-full overflow-hidden ${sizeClasses[size]}`}>
        <div
          className={`h-full rounded-full transition-all duration-300 ${barColor ?? ''}`}
          style={{
            width: `${clamped}%`,
            ...(color ? { backgroundColor: color } : {}),
          }}
        />
      </div>
    </div>
  )
}
