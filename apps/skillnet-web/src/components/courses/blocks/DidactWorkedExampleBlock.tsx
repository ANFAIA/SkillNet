import { lazy, Suspense } from 'react'
import { useIntl } from 'react-intl'

const WorkedExample = lazy(() => import('../../../../vendor/didact/source/packages/core/src/components/generative-learning').then((module) => ({ default: module.WorkedExample })))

export function DidactWorkedExampleBlock({ problem, steps, summary }: { problem: string; steps: string[]; summary: string }) {
  const intl = useIntl()

  return (
    <div className="didact-scope">
      <Suspense fallback={<div className="h-20 animate-pulse rounded-md bg-bg-muted" />}><WorkedExample
        problem={problem}
        steps={steps.map((step, index) => ({ id: `worked-${index}`, title: intl.formatMessage({ id: 'didact.workedExample.step' }, { number: index + 1 }), content: step }))}
        summary={summary}
        mode="progressive"
      /></Suspense>
    </div>
  )
}
