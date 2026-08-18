import { useIntl } from 'react-intl'
import { INLINE_SURFACE, BLOCK_TITLE } from './rhythm'
import { useArtifactAsset } from './useArtifactAsset'

/**
 * In-lesson podcast player (broker-injected `PodcastPlayer(artifact_id, title)`, §runtime/8).
 *
 * The media broker widens a node's render prompt with this component only when the node has
 * a ready podcast artefact and the learner prefers audio; the model then emits it inside the
 * episode program. Unlike the course-surface `PodcastPlayer` (which is fed the whole grounded
 * `spec_json` — transcript + citations), this one arrives with only an `artifact_id` and a
 * `title`, so it renders the essential thing: a working audio player over the artefact's mp3,
 * fetched through the credentialed asset route. Loading and error states keep the lesson from
 * ever showing a raw tag or a blank panel.
 */
export interface PodcastPlayerBlockProps {
  artifactId: string
  title: string
}

export function PodcastPlayerBlock({ artifactId, title }: PodcastPlayerBlockProps) {
  const intl = useIntl()
  const { url, loading, error } = useArtifactAsset(artifactId)

  return (
    <div data-no-explain="" className={`${INLINE_SURFACE} bg-bg-subtle`}>
      <div className="mb-3 flex items-center gap-2">
        <span
          className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"
          aria-hidden="true"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
            <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
            <line x1="12" y1="19" x2="12" y2="23" />
          </svg>
        </span>
        <h3 className={BLOCK_TITLE + ' mb-0'}>
          {title?.trim() ? title : intl.formatMessage({ id: 'podcast.title' })}
        </h3>
      </div>

      {loading && (
        <p className="text-sm text-text-muted">
          {intl.formatMessage({ id: 'podcast.loading' })}
        </p>
      )}
      {error && (
        <p className="text-sm text-danger" role="alert">
          {intl.formatMessage({ id: 'podcast.unavailable' })}
        </p>
      )}
      {url && !error && (
        <audio className="w-full" controls src={url} data-testid="podcast-block-audio">
          <track kind="captions" />
        </audio>
      )}
    </div>
  )
}
