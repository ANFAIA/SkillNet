type MetricColor = 'blue' | 'green' | 'orange' | 'purple'

export interface MetricCardProps {
  value: string
  label: string
  icon: React.ReactNode
  color: MetricColor
  className?: string
}

const colorClasses: Record<MetricColor, string> = {
  blue: 'before:bg-metric-blue',
  green: 'before:bg-metric-green',
  orange: 'before:bg-metric-orange',
  purple: 'before:bg-metric-purple',
}

export function MetricCard({ value, label, icon, color, className = '' }: MetricCardProps) {
  return (
    <div
      className={`relative min-w-0 overflow-hidden rounded-xl border border-border bg-surface p-5 before:absolute before:inset-x-0 before:top-0 before:h-0.5 ${colorClasses[color]} ${className}`}
    >
      <div className="flex min-w-0 items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="truncate text-sm text-text-secondary">{label}</p>
          <p className="mt-2 truncate text-2xl font-semibold tracking-tight text-text">{value}</p>
        </div>
        <div className="shrink-0 text-text-muted">{icon}</div>
      </div>
    </div>
  )
}
