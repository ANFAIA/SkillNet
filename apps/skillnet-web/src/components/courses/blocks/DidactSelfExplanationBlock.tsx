import { lazy, Suspense } from 'react'

const SelfExplanationPrompt = lazy(() => import('../../../../vendor/didact/source/packages/core/src/components/generative-learning').then((module) => ({ default: module.SelfExplanationPrompt })))

export function DidactSelfExplanationBlock({ prompt, scaffold, model }: { prompt: string; scaffold: string[]; model: string }) {
  return (
    <div className="didact-scope">
      <Suspense fallback={<div className="h-20 animate-pulse rounded-md bg-bg-muted" />}><SelfExplanationPrompt prompt={prompt} scaffolds={scaffold} modelExplanation={model || undefined} /></Suspense>
    </div>
  )
}
