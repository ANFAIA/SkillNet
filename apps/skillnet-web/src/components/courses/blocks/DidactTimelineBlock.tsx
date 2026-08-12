import { lazy, Suspense } from 'react'

const Timeline = lazy(() => import('../../../../vendor/didact/source/packages/core/src/components/timeline').then((module) => ({ default: module.Timeline })))

export function DidactTimelineBlock({ label, steps, details }: { label: string; steps: string[]; details: string[] }) {
  return (
    <section className="didact-scope" aria-label={label}>
      <Suspense fallback={<div className="h-20 animate-pulse rounded-md bg-bg-muted" />}><Timeline steps={steps.map((step, index) => ({ id: `step-${index}`, title: step, description: details[index] || undefined }))} /></Suspense>
    </section>
  )
}
