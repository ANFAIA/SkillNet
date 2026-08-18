import { DidactActivityBlock } from '../../../components/courses/blocks/DidactActivityBlock'
import type { ExperienceAdapterProps } from '../registry'

function implementationId(implementationRef: string): string {
  const separator = implementationRef.lastIndexOf('@')
  return separator > 0 ? implementationRef.slice(0, separator) : implementationRef
}

export function DidactExperienceAdapter({ reference }: ExperienceAdapterProps) {
  const componentId = reference.componentId ?? implementationId(reference.implementationRef)
  const activityId = reference.activityId ?? reference.definitionRef
  const legacyReference = Boolean(reference.activityId || reference.componentId)
  // A materialized experience carries a binding whose id differs from the activity
  // definition it implements. An authored activity referenced directly (sort, matching,
  // categorize, word-bank…) has no binding: the runtime reuses the activity id for both
  // refs. Only route through the attempt/binding path when a real binding exists; otherwise
  // evaluate the authored activity directly.
  const hasBinding = !legacyReference && reference.experienceId !== reference.definitionRef

  return (
    <DidactActivityBlock
      activityId={activityId}
      componentId={componentId}
      bindingId={hasBinding ? reference.experienceId : undefined}
    />
  )
}
