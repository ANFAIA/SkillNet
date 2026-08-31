import { Bar, BarChart, CartesianGrid, Tooltip, XAxis, YAxis } from 'recharts'
import { useIntl } from 'react-intl'
import type { TalentCourseSummary } from '../../api/talent'
import { Card, CardTitle, ChartContainer, EmptyState, type ChartConfig } from '../ui'

type CourseProgressChartProps = {
  courses: TalentCourseSummary[]
}

/** Message ids for the stacked series, shared by the chart config, the bars and the legend. */
const seriesMessageIds = {
  completed: 'talent.table.completed',
  inProgress: 'talent.table.inProgress',
  notStarted: 'talent.filters.statusNotStarted',
} as const

export function CourseProgressChart({ courses }: CourseProgressChartProps) {
  const intl = useIntl()
  const visible = [...courses]
    .filter((course) => course.assigned_count > 0)
    .sort((a, b) => b.assigned_count - a.assigned_count || a.title.localeCompare(b.title))
    .slice(0, 5)
  const data = visible.map((course) => ({
    title: course.title.length > 24 ? `${course.title.slice(0, 23)}…` : course.title,
    fullTitle: course.title,
    completed: course.completed_count,
    inProgress: course.in_progress_count,
    notStarted: Math.max(0, course.assigned_count - course.completed_count - course.in_progress_count),
  }))
  const config: ChartConfig = {
    completed: { label: intl.formatMessage({ id: seriesMessageIds.completed }), color: 'var(--color-success)' },
    inProgress: { label: intl.formatMessage({ id: seriesMessageIds.inProgress }), color: 'var(--color-warning)' },
    notStarted: { label: intl.formatMessage({ id: seriesMessageIds.notStarted }), color: 'var(--color-bg-muted)' },
  }

  return (
    <Card className="h-full rounded-lg">
      <CardTitle>{intl.formatMessage({ id: 'talent.progressChart.title' })}</CardTitle>
      <p className="mt-1 text-sm text-text-muted">{intl.formatMessage({ id: 'talent.progressChart.description' })}</p>
      {visible.length === 0 ? (
        <EmptyState title={intl.formatMessage({ id: 'talent.progressChart.emptyTitle' })} description={intl.formatMessage({ id: 'talent.progressChart.emptyDescription' })} />
      ) : (
        <>
          <ChartContainer config={config} className="mt-4 h-[220px]" aria-label={intl.formatMessage({ id: 'talent.progressChart.ariaLabel' })}>
            <BarChart accessibilityLayer data={data} layout="vertical" margin={{ left: 0, right: 8 }}>
              <CartesianGrid horizontal={false} />
              <XAxis type="number" allowDecimals={false} axisLine={false} tickLine={false} />
              <YAxis dataKey="title" type="category" width={126} axisLine={false} tickLine={false} tickMargin={8} />
              <Tooltip cursor={{ fill: 'var(--color-bg-subtle)' }} labelFormatter={(_, payload) => payload?.[0]?.payload.fullTitle ?? ''} />
              <Bar dataKey="completed" name={config.completed.label} stackId="progress" fill="var(--color-completed)" radius={[4, 0, 0, 4]} />
              <Bar dataKey="inProgress" name={config.inProgress.label} stackId="progress" fill="var(--color-inProgress)" />
              <Bar dataKey="notStarted" name={config.notStarted.label} stackId="progress" fill="var(--color-notStarted)" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ChartContainer>
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted" aria-hidden="true">
            {Object.entries(config).map(([key, item]) => <span key={key} className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm" style={{ backgroundColor: item.color }} />{item.label}</span>)}
          </div>
          <div className="sr-only">
            {visible.map((course) => {
              const completion = course.assigned_count > 0 ? Math.round((course.completed_count / course.assigned_count) * 100) : 0
              const inProgress = course.assigned_count > 0 ? Math.round((course.in_progress_count / course.assigned_count) * 100) : 0
              return (
                <div key={course.course_id} role="img" aria-label={intl.formatMessage({ id: 'talent.progressChart.courseAriaLabel' }, { title: course.title, completion, inProgress })}>
                  <span>{course.title}</span><span>{course.completed_count}/{course.assigned_count}</span>
                </div>
              )
            })}
          </div>
        </>
      )}
    </Card>
  )
}
