import { useIntl } from 'react-intl'
import type { MediaArtifactRead } from '../../api/media'
import { PodcastPlayer, type PodcastCitation, type PodcastTurn } from './PodcastPlayer'
import { VideoOverview, type VideoSlideSpec } from './VideoOverview'
import { Infographic, type InfographicCitation, type InfographicSectionSpec } from './Infographic'
import { SlideDeck, type SlideCitation, type SlideSpec } from './SlideDeck'

export function CourseArtifactView({ artifact }: { artifact: MediaArtifactRead }) {
  const intl = useIntl()
  const spec = artifact.spec_json ?? {}

  switch (artifact.kind) {
    case 'podcast':
      return <PodcastPlayer artifactId={artifact.id} turns={(spec.turns as PodcastTurn[]) ?? []} citations={(spec.citations as PodcastCitation[]) ?? []} format={spec.format as string | undefined} />
    case 'video':
      return <VideoOverview artifactId={artifact.id} slides={(spec.slides as VideoSlideSpec[]) ?? []} citations={(spec.citations as SlideCitation[]) ?? []} theme={spec.theme as string | undefined} />
    case 'infographic':
      return <Infographic artifactId={artifact.id} title={(spec.title as string) ?? ''} subtitle={spec.subtitle as string | null | undefined} sections={(spec.sections as InfographicSectionSpec[]) ?? []} citations={(spec.citations as InfographicCitation[]) ?? []} orientation={spec.orientation as 'portrait' | 'landscape' | undefined} hasImage={(spec.has_image as boolean | undefined) ?? false} />
    case 'slides':
      return <SlideDeck artifactId={artifact.id} slides={(spec.slides as SlideSpec[]) ?? []} citations={(spec.citations as SlideCitation[]) ?? []} theme={spec.theme as string | undefined} />
    default:
      return <p className="text-sm text-text-muted">{intl.formatMessage({ id: 'overviews.unsupported' })}</p>
  }
}
