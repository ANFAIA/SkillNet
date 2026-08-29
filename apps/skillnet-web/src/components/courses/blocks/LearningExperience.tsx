import { useEffect, useState } from 'react'
import type { ComponentType } from 'react'

import { experienceAdapterRegistry } from '../../../lib/experiences'
import type { ExperienceAdapterProps } from '../../../lib/experiences'
import type { LearningExperienceReference } from '../../../types/learning-experience'
import { useSolveStepWhen } from './StepperContext'

function ExperienceStatus({ kind, children }: { kind: 'loading' | 'failed'; children: string }) {
  // The step is already closed if this experience evaluates (`kit/solvableSteps.ts`), and
  // that was decided by reading the program, before knowing whether the adapter even
  // exists. Nobody is going to open it from an error box, so the exit belongs here.
  useSolveStepWhen(kind === 'failed')
  return (
    <div
      className="rounded-lg border border-border bg-bg-subtle px-4 py-3 text-sm text-text-secondary"
      data-learning-experience-status={kind}
      role={kind === 'failed' ? 'alert' : 'status'}
      aria-live={kind === 'loading' ? 'polite' : undefined}
    >
      {children}
    </div>
  )
}

export function LearningExperience({
  experienceId,
  implementationRef,
  definitionRef,
  publicDefinition,
  activityId,
  componentId,
}: LearningExperienceReference) {
  const [Renderer, setRenderer] = useState<ComponentType<ExperienceAdapterProps> | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let active = true
    setRenderer(null)
    setFailed(false)

    const pending = experienceAdapterRegistry.load(implementationRef)
    if (!pending) {
      setFailed(true)
      return () => { active = false }
    }

    void pending
      .then((adapter) => {
        if (active) setRenderer(() => adapter.Renderer)
      })
      .catch(() => {
        if (active) setFailed(true)
      })

    return () => { active = false }
  }, [implementationRef])

  if (!experienceId || !implementationRef || !definitionRef) {
    return <ExperienceStatus kind="failed">La referencia de esta experiencia no es válida.</ExperienceStatus>
  }
  if (failed) {
    return <ExperienceStatus kind="failed">Esta experiencia no está disponible.</ExperienceStatus>
  }
  if (!Renderer) return <ExperienceStatus kind="loading">Cargando experiencia…</ExperienceStatus>

  const reference = {
    experienceId,
    implementationRef,
    definitionRef,
    publicDefinition,
    activityId,
    componentId,
  }
  return <Renderer reference={reference} />
}
