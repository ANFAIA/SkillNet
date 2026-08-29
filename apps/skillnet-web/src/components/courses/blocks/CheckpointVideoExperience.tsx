import { useIntl } from 'react-intl'

import type { CheckpointVideoDefinition } from '../../../lib/experiences/adapters/checkpoint-video-definition'

export function CheckpointVideoExperience({
  definition,
}: {
  definition: CheckpointVideoDefinition
}) {
  const intl = useIntl()
  return (
    <figure className="w-full max-w-3xl space-y-3" data-experience-provider="media">
      <figcaption className="text-sm font-semibold text-text-primary">
        {definition.title}
      </figcaption>
      <video
        className="w-full rounded-lg border border-border bg-black"
        src={definition.src}
        controls
        playsInline
        preload="metadata"
        aria-label={definition.title}
      >
        {definition.captionsSrc ? (
          <track
            kind="captions"
            src={definition.captionsSrc}
            srcLang={definition.captionsLanguage ?? 'es'}
            label={intl.formatMessage({ id: 'experience.video.captions' })}
            default
          />
        ) : null}
      </video>
      {definition.transcript ? (
        <details className="rounded-lg border border-border bg-bg px-4 py-3 text-sm text-text-secondary">
          <summary className="cursor-pointer font-medium text-text-primary">
            {intl.formatMessage({ id: 'experience.video.readTranscript' })}
          </summary>
          <p className="mt-3 whitespace-pre-wrap">{definition.transcript}</p>
        </details>
      ) : null}
      {definition.checkpointText ? (
        <section
          className="rounded-lg border border-border bg-bg-subtle px-4 py-3 text-sm text-text-primary"
          aria-label={intl.formatMessage({ id: 'experience.video.checkpoint' })}
        >
          {definition.checkpointText}
        </section>
      ) : null}
    </figure>
  )
}

