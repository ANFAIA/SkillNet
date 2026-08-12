import { MetricCard } from '../ui'
import { TalentMetricIcon } from './TalentMetricIcon'

type TalentSummaryProps = {
  people: number
  assigned: number
  inProgress: number
  completed: number
  skills: number
}

type SummaryKey = keyof TalentSummaryProps
type SummaryKind = 'people' | 'enrollments' | 'progress' | 'completed' | 'skills'

const summaryItems: Array<{ key: SummaryKey; label: string; kind: SummaryKind }> = [
  { key: 'people', label: 'Personas visibles', kind: 'people' },
  { key: 'assigned', label: 'Matrículas', kind: 'enrollments' },
  { key: 'inProgress', label: 'En curso', kind: 'progress' },
  { key: 'completed', label: 'Completadas', kind: 'completed' },
  { key: 'skills', label: 'Habilidades', kind: 'skills' },
]

export function TalentSummary(props: TalentSummaryProps) {
  return (
    <section className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5" aria-label="Resumen del talento visible">
      {summaryItems.map((item) => (
        <MetricCard
          key={item.key}
          value={String(props[item.key])}
          label={item.label}
          icon={<TalentMetricIcon kind={item.kind} />}
        />
      ))}
    </section>
  )
}
