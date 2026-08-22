import { useIntl } from 'react-intl'
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

const summaryItems: Array<{ key: SummaryKey; labelId: string; kind: SummaryKind }> = [
  { key: 'people', labelId: 'talent.summary.peopleVisible', kind: 'people' },
  { key: 'assigned', labelId: 'talent.summary.enrollments', kind: 'enrollments' },
  { key: 'inProgress', labelId: 'talent.summary.inProgress', kind: 'progress' },
  { key: 'completed', labelId: 'talent.summary.completed', kind: 'completed' },
  { key: 'skills', labelId: 'talent.summary.skills', kind: 'skills' },
]

export function TalentSummary(props: TalentSummaryProps) {
  const intl = useIntl()
  return (
    <section className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5" aria-label={intl.formatMessage({ id: 'talent.summary.ariaLabel' })}>
      {summaryItems.map((item) => (
        <MetricCard
          key={item.key}
          value={String(props[item.key])}
          label={intl.formatMessage({ id: item.labelId })}
          icon={<TalentMetricIcon kind={item.kind} />}
        />
      ))}
    </section>
  )
}
