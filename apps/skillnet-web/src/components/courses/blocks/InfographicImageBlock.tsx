import { useIntl } from 'react-intl'
import { INLINE_SURFACE, BLOCK_TITLE } from './rhythm'
import { useArtifactAsset } from './useArtifactAsset'

/**
 * In-lesson infographic image (broker-injected `InfographicImage(artifact_id, alt)`,
 * §runtime/8).
 *
 * The media broker widens a node's render prompt with this component only when the node has a
 * ready infographic artefact and the learner prefers visuals; the model then emits it inside
 * the episode program. Unlike the course-surface `Infographic` (fed the whole grounded
 * `spec_json` — the stat/section grid + citations), this one arrives with only an
 * `artifact_id` and an accessible `alt`, so it renders the essential thing: the generated
 * poster image, responsive, fetched through the credentialed asset route. Loading and error
 * states keep the lesson from ever showing a broken image or a blank panel.
 */
export interface InfographicImageBlockProps {
  artifactId: string
  alt: string
}

export function InfographicImageBlock({ artifactId, alt }: InfographicImageBlockProps) {
  const intl = useIntl()
  const { url, loading, error } = useArtifactAsset(artifactId)
  const altText = alt?.trim() ? alt : intl.formatMessage({ id: 'infographic.title' })

  return (
    <div data-no-explain="" className={`${INLINE_SURFACE} bg-bg-subtle`}>
      <div className="mb-3 flex items-center gap-2">
        <span
          className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"
          aria-hidden="true"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <polyline points="21 15 16 10 5 21" />
          </svg>
        </span>
        <h3 className={BLOCK_TITLE + ' mb-0'}>
          {intl.formatMessage({ id: 'infographic.title' })}
        </h3>
      </div>

      {loading && (
        <p className="text-sm text-text-muted">
          {intl.formatMessage({ id: 'infographic.loading' })}
        </p>
      )}
      {error && (
        <p className="text-sm text-danger" role="alert">
          {intl.formatMessage({ id: 'infographic.unavailable' })}
        </p>
      )}
      {url && !error && (
        <figure className="flex justify-center rounded-xl border border-border bg-bg overflow-hidden p-2">
          <img
            src={url}
            alt={altText}
            data-testid="infographic-block-image"
            className="mx-auto block h-auto max-h-[26rem] w-auto max-w-full object-contain"
          />
        </figure>
      )}
    </div>
  )
}
