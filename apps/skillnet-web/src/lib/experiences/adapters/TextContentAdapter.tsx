import { TextContentBlock } from '../../../components/courses/blocks/TextContentBlock'
import type { ExperienceAdapterProps } from '../registry'
import { validateTextContentDefinition } from './text-content-definition'

export function TextContentAdapter({ reference }: ExperienceAdapterProps) {
  const validated = validateTextContentDefinition(reference.publicDefinition)
  if (!validated.ok) {
    return (
      <div
        className="rounded-lg border border-border bg-bg-subtle px-4 py-3 text-sm text-text-secondary"
        role="alert"
        data-learning-experience-status="failed"
      >
        El contenido breve de esta experiencia no es válido.
      </div>
    )
  }

  return (
    <TextContentBlock
      text={validated.definition.content}
      variant={validated.definition.variant}
    />
  )
}

