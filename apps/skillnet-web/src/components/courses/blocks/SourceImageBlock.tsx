import { useIntl } from 'react-intl'
import { INLINE_SURFACE, BLOCK_TITLE } from './rhythm'
import { useSourceImageAsset } from './useArtifactAsset'

/**
 * An image taken from *inside* the customer's own source document, shown as it is
 * (broker-injected `SourceImage(image_id, alt, caption, document_id)`).
 *
 * ## Why a picture and not prose
 *
 * The pipeline's rule is that a **diagram** gets rebuilt as interactive SkillNet content
 * and a **screenshot** gets kept. A screenshot's information is spatial — "the *Devolver*
 * button, top right" — and any prose rewrite of it is strictly worse than the picture.
 * This block is the *kept* half of that rule. `image_source_policy` on the course
 * overrides it in either direction; the decision itself is the backend's.
 *
 * ## Why the caption is rendered and the infographic's is not
 *
 * `InfographicImageBlock` shows a poster SkillNet generated, so provenance lives on the
 * course surface with the rest of the artefact's grounding. Here the caption ("Fuente:
 * manual.pdf, pág. 7") is the point: it is the legal record of where the image came from
 * and, more usefully, the signal to the learner that this is *their organisation's own*
 * diagram and not something a model drew. So it is on screen, under the image, always —
 * with a generic fallback when the broker sends no provenance string, because "this came
 * out of the document" is still worth saying.
 *
 * States mirror the sibling block exactly: an image that will not load shows an inline
 * notice and nothing else. The lesson around it is never broken by a missing file.
 */
export interface SourceImageBlockProps {
  /** `source_images.id`. */
  imageId: string
  /** Accessible description of what the image shows. */
  alt: string
  /** Provenance line, already formatted by the broker. May be empty. */
  caption: string
  /**
   * `documents.id` that owns the image. The asset route is document-scoped, so this is
   * not optional in practice — see the note on the prop schema in `kit/schemas.ts`.
   */
  documentId: string
}

export function SourceImageBlock({ imageId, alt, caption, documentId }: SourceImageBlockProps) {
  const intl = useIntl()
  const { url, loading, error } = useSourceImageAsset(documentId, imageId)
  const altText = alt?.trim() ? alt : intl.formatMessage({ id: 'sourceImage.title' })
  const captionText = caption?.trim()
    ? caption
    : intl.formatMessage({ id: 'sourceImage.fromDocument' })

  return (
    <div data-no-explain="" className={`${INLINE_SURFACE} bg-bg-subtle`}>
      <div className="mb-3 flex items-center gap-2">
        <span
          className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"
          aria-hidden="true"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
            <polyline points="14 2 14 8 20 8" />
            <circle cx="9.5" cy="13.5" r="1.5" />
            <path d="m20 18-3.5-3.5a1.5 1.5 0 0 0-2.12 0L9 20" />
          </svg>
        </span>
        <h3 className={BLOCK_TITLE + ' mb-0'}>
          {intl.formatMessage({ id: 'sourceImage.title' })}
        </h3>
      </div>

      {loading && (
        <p className="text-sm text-text-muted">
          {intl.formatMessage({ id: 'sourceImage.loading' })}
        </p>
      )}
      {error && (
        <p className="text-sm text-danger" role="alert">
          {intl.formatMessage({ id: 'sourceImage.unavailable' })}
        </p>
      )}
      {url && !error && (
        <figure className="rounded-xl border border-border bg-bg overflow-hidden p-2">
          <img
            src={url}
            alt={altText}
            data-testid="source-image-block-image"
            className="mx-auto block h-auto max-h-[26rem] w-auto max-w-full object-contain"
          />
          <figcaption className="mt-2 px-1 text-center text-xs text-text-muted">
            {captionText}
          </figcaption>
        </figure>
      )}
    </div>
  )
}
