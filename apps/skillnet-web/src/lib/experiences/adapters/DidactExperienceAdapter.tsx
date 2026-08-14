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

  return (
    <DidactActivityBlock
      activityId={activityId}
      componentId={componentId}
      bindingId={legacyReference ? undefined : reference.experienceId}
    />
  )
}
