import { Cell, Label, Pie, PieChart, Tooltip } from 'recharts'
import { Card, CardTitle, ChartContainer, type ChartConfig } from '../ui'

type EnrollmentDistributionChartProps = {
  assigned: number
  inProgress: number
  completed: number
}

export function EnrollmentDistributionChart({ assigned, inProgress, completed }: EnrollmentDistributionChartProps) {
  const notStarted = Math.max(0, assigned - inProgress - completed)
  const data = [
    { key: 'notStarted', label: 'Sin iniciar', value: notStarted, color: 'var(--color-text-muted)' },
    { key: 'inProgress', label: 'En curso', value: inProgress, color: 'var(--color-warning)' },
    { key: 'completed', label: 'Completadas', value: completed, color: 'var(--color-success)' },
  ]
  const config: ChartConfig = {
    notStarted: { label: 'Sin iniciar', color: 'var(--color-text-muted)' },
    inProgress: { label: 'En curso', color: 'var(--color-warning)' },
    completed: { label: 'Completadas', color: 'var(--color-success)' },
  }
  const chartData = assigned > 0 ? data : [{ key: 'empty', label: 'Sin datos', value: 1, color: 'var(--color-bg-muted)' }]

  return (
    <Card className="h-full rounded-lg">
      <CardTitle>Distribución de matrículas</CardTitle>
      <p className="mt-1 text-sm text-text-muted">Situación de las asignaciones visibles.</p>
      <div className="mt-4 grid grid-cols-[150px_minmax(0,1fr)] items-center gap-4">
        <ChartContainer config={config} className="h-[150px]" aria-label={`${assigned} matrículas: ${notStarted} sin iniciar, ${inProgress} en curso y ${completed} completadas`}>
          <PieChart accessibilityLayer>
            <Tooltip cursor={false} formatter={(value, name) => [value, config[String(name)]?.label ?? name]} />
            <Pie data={chartData} dataKey="value" nameKey="key" innerRadius={48} outerRadius={66} strokeWidth={0}>
              {chartData.map((item) => <Cell key={item.key} fill={item.color} />)}
              <Label position="center" content={() => (
                <text x="50%" y="50%" textAnchor="middle" dominantBaseline="middle">
                  <tspan x="50%" dy="-0.2em" className="fill-text text-2xl font-semibold">{assigned}</tspan>
                  <tspan x="50%" dy="1.5em" className="fill-text-muted text-xs">matrículas</tspan>
                </text>
              )} />
            </Pie>
          </PieChart>
        </ChartContainer>
        <dl className="space-y-3">
          {data.map((segment) => (
            <div key={segment.key} className="flex items-center justify-between gap-3">
              <dt className="flex items-center gap-2 text-sm text-text-secondary">
                <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: segment.color }} aria-hidden="true" />
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
