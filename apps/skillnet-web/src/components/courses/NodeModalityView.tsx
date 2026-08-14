import { useIntl } from 'react-intl'
import type { MediaArtifactRead } from '../../api/media'
import { PodcastPlayer, type PodcastCitation, type PodcastTurn } from './PodcastPlayer'
import { VideoOverview, type VideoSlideSpec } from './VideoOverview'
import type { SlideCitation } from './SlideDeck'

export function NodeModalityView({ artifact }: { artifact: MediaArtifactRead }) {
  const intl = useIntl()
  const spec = artifact.spec_json ?? {}
  if (artifact.kind === 'podcast') {
    return (
      <PodcastPlayer
        artifactId={artifact.id}
        turns={(spec.turns as PodcastTurn[]) ?? []}
        citations={(spec.citations as PodcastCitation[]) ?? []}
        format={spec.format as string | undefined}
        title={intl.formatMessage({ id: 'node.modality.audioTitle' })}
      />
    )
  }
  return (
    <VideoOverview
      artifactId={artifact.id}
      slides={(spec.slides as VideoSlideSpec[]) ?? []}
      citations={(spec.citations as SlideCitation[]) ?? []}
      theme={spec.theme as string | undefined}
      title={intl.formatMessage({ id: 'node.modality.videoTitle' })}
    />
  )
}
