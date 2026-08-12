import { Card, CardTitle } from '../ui'

type EnrollmentDistributionChartProps = {
  assigned: number
  inProgress: number
  completed: number
}

export function EnrollmentDistributionChart({ assigned, inProgress, completed }: EnrollmentDistributionChartProps) {
  const notStarted = Math.max(0, assigned - inProgress - completed)
  const total = Math.max(assigned, 1)
  const segments = [
    { label: 'Sin iniciar', value: notStarted, strokeClass: 'stroke-text-muted', dotClass: 'border-text-muted' },
    { label: 'En curso', value: inProgress, strokeClass: 'stroke-warning', dotClass: 'border-warning' },
    { label: 'Completadas', value: completed, strokeClass: 'stroke-accent', dotClass: 'border-accent' },
  ]
  let offset = 0

  return (
    <Card className="h-full">
      <CardTitle>Distribución de matrículas</CardTitle>
      <p className="mt-1 text-sm text-text-muted">Situación actual de las asignaciones visibles.</p>
      <div className="mt-5 grid grid-cols-[132px_minmax(0,1fr)] items-center gap-5">
        <div className="relative h-[132px] w-[132px]" role="img" aria-label={`${assigned} matrículas: ${notStarted} sin iniciar, ${inProgress} en curso y ${completed} completadas`}>
          <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90" aria-hidden="true">
            <circle cx="60" cy="60" r="43" fill="none" strokeWidth="14" className="stroke-bg-muted" />
            {segments.map((segment) => {
              const length = assigned > 0 ? (segment.value / total) * 100 : 0
              const circle = (
                <circle
                  key={segment.label}
                  cx="60"
                  cy="60"
                  r="43"
                  pathLength="100"
                  fill="none"
                  strokeWidth="14"
                  strokeLinecap="butt"
                  strokeDasharray={`${length} ${100 - length}`}
                  strokeDashoffset={-offset}
                  className={segment.strokeClass}
                />
              )
              offset += length
              return circle
            })}
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-2xl font-semibold text-text tabular-nums">{assigned}</span>
            <span className="text-xs text-text-muted">matrículas</span>
          </div>
        </div>
        <dl className="space-y-3">
          {segments.map((segment) => (
            <div key={segment.label} className="flex items-center justify-between gap-3">
              <dt className="flex items-center gap-2 text-sm text-text-secondary">
                <span className={`h-2.5 w-2.5 rounded-sm border-[3px] ${segment.dotClass}`} aria-hidden="true" />
                {segment.label}
              </dt>
              <dd className="text-sm font-medium text-text tabular-nums">{segment.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </Card>
  )
}
