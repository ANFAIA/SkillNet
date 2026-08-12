export interface MetricCardProps {
  value: string
  label: string
  icon: React.ReactNode
  className?: string
}

export function MetricCard({ value, label, icon, className = '' }: MetricCardProps) {
  return (
    <div
      className={`min-w-0 rounded-lg border border-border bg-surface p-5 ${className}`}
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
