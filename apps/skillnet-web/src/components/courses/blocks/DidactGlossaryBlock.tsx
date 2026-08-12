import { lazy, Suspense } from 'react'

const Glossary = lazy(() => import('../../../../vendor/didact/source/packages/core/src/components/glossary').then((module) => ({ default: module.Glossary })))

export function DidactGlossaryBlock({ title, terms, definitions }: { title: string; terms: string[]; definitions: string[] }) {
  const entries = terms.map((term, index) => ({
    id: `term-${index}`,
    term,
    definition: definitions[index] ?? '',
  }))
  return <section className="didact-scope" aria-label={title}><Suspense fallback={<div className="h-20 animate-pulse rounded-md bg-bg-muted" />}><Glossary entries={entries} /></Suspense></section>
}
