import { useIntl } from 'react-intl'
import type {
  DetailPreference,
  ImagePreference,
  PresentationPreference,
} from '../../api/onboarding'
import { SettingsIcon } from './SettingsIcon'

export function LearningPreferencePreview({
  presentation,
  detail,
  images,
}: {
  presentation: PresentationPreference
  detail: DetailPreference
  images: ImagePreference
}) {
  const intl = useIntl()
  const showMedia = images !== 'avoid'
  const showPractice = presentation === 'interactive'
  const lineCount = detail === 'concise' ? 2 : detail === 'detailed' ? 5 : 3
  const mediaHeight =
    images === 'prefer' || presentation === 'visual'
      ? 'min-h-24'
      : presentation === 'textual' || presentation === 'interactive'
        ? 'min-h-10'
        : 'min-h-16'

  return (
    <aside className="flex h-full min-w-0 flex-col rounded-lg border border-border bg-bg-subtle p-3.5" aria-label={intl.formatMessage({ id: 'learningPreferences.preview' })}>
      <span className="text-xs text-text-muted">
        {intl.formatMessage({ id: 'learningPreferences.preview' })}
      </span>

      <div className="mt-3 flex min-h-0 flex-1 flex-col gap-2 rounded-lg border border-border bg-surface p-3.5">
        <div className="flex items-center justify-between text-[11px] text-text-muted">
          <span className="font-medium text-primary">
            {intl.formatMessage({ id: 'learningPreferences.preview.microLesson' })}
          </span>
          <span>{intl.formatMessage({ id: 'learningPreferences.preview.duration' })}</span>
        </div>

        <strong className="text-sm font-medium text-text">
          {intl.formatMessage({ id: 'learningPreferences.preview.title' })}
        </strong>

        <div className="space-y-1.5" aria-hidden="true">
          {Array.from({ length: lineCount }, (_, index) => (
            <span
              key={index}
              className={`block h-1 rounded-full bg-border-strong ${index === lineCount - 1 ? 'w-3/4' : 'w-full'}`}
            />
          ))}
        </div>

        {showMedia && (
          <div className={`grid flex-1 place-items-center rounded-lg bg-primary-subtle text-primary ${mediaHeight}`}>
            <span className="flex items-center gap-2 text-xs font-medium">
              <SettingsIcon name="shield" size={22} />
              {intl.formatMessage({ id: 'learningPreferences.preview.media' })}
            </span>
          </div>
        )}

        {showPractice && (
          <div className="rounded-lg border border-border p-2.5">
            <span className="text-[11px] text-text">
              {intl.formatMessage({ id: 'learningPreferences.preview.practice' })}
            </span>
            <div className="mt-2 flex gap-1.5" aria-hidden="true">
              <span className="h-3 flex-1 rounded bg-bg-muted" />
              <span className="h-3 flex-1 rounded bg-bg-muted" />
              <span className="h-3 flex-1 rounded bg-bg-muted" />
            </div>
          </div>
        )}

        <div
          aria-hidden="true"
          className="flex cursor-default items-center justify-center gap-1.5 rounded-lg bg-bg-muted px-3 py-2 text-xs font-medium text-text-secondary"
        >
          {intl.formatMessage({ id: 'learningPreferences.preview.continue' })}
          <SettingsIcon name="arrowRight" size={12} />
        </div>
      </div>

      <div className="mt-2.5 flex flex-wrap gap-1.5 text-[11px] text-text-muted" aria-live="polite">
        <span className="rounded-md bg-bg-muted px-2 py-1">
          {intl.formatMessage({ id: `learningPreferences.presentation.${presentation}` })}
        </span>
        <span className="rounded-md bg-bg-muted px-2 py-1">
          {intl.formatMessage({ id: `learningPreferences.detail.${detail}` })}
        </span>
        <span className="rounded-md bg-bg-muted px-2 py-1">
          {intl.formatMessage({ id: `learningPreferences.images.${images}` })}
        </span>
      </div>
    </aside>
  )
}
