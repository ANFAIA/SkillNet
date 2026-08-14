import { CheckpointVideoExperience } from '../../../components/courses/blocks/CheckpointVideoExperience'
import type { ExperienceAdapterProps } from '../registry'
import { validateCheckpointVideoDefinition } from './checkpoint-video-definition'

export function CheckpointVideoAdapter({ reference }: ExperienceAdapterProps) {
  const validated = validateCheckpointVideoDefinition(reference.publicDefinition)
  if (!validated.ok) {
    return (
      <div
        className="rounded-lg border border-border bg-bg-subtle px-4 py-3 text-sm text-text-secondary"
        role="alert"
        data-learning-experience-status="failed"
      >
        El vídeo necesita una fuente segura y subtítulos o transcripción.
      </div>
    )
  }

  return <CheckpointVideoExperience definition={validated.definition} />
}

