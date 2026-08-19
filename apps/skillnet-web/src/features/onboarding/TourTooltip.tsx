import { useIntl } from 'react-intl'
import type { TooltipRenderProps } from 'react-joyride'
import { Button } from '../../components/ui'

/**
 * Custom joyride tooltip so the tour reads as part of SkillNet, not as react-joyride.
 * It is built from the same design tokens as every other surface — `bg-surface`,
 * `border-border`, `rounded-xl`, `shadow-lg`, `text-text*` — so it is theme-aware
 * (light/dark + accent) for free through the CSS variables, and it reuses the app
 * `Button`. All copy is i18n'd; step title/body arrive as message ids on `step`.
 */
export function TourTooltip({
  index,
  size,
  step,
  backProps,
  primaryProps,
  skipProps,
  closeProps,
  tooltipProps,
  isLastStep,
}: TooltipRenderProps) {
  const intl = useIntl()
  // `title`/`content` carry the i18n ids we set on the joyride step.
  const titleId = typeof step.title === 'string' ? step.title : ''
  const bodyId = typeof step.content === 'string' ? step.content : ''

  return (
    <div
      {...tooltipProps}
      className="w-[19rem] max-w-[calc(100vw-2rem)] rounded-xl border border-border bg-surface p-4 text-left shadow-lg"
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="mb-1 text-[0.7rem] font-medium uppercase tracking-wide text-primary">
            {intl.formatMessage(
              { id: 'onboarding.tour.progress' },
              { current: index + 1, total: size },
            )}
          </p>
          {titleId && (
            <h2 className="text-sm font-semibold text-text">
              {intl.formatMessage({ id: titleId })}
            </h2>
          )}
        </div>
        <button
          {...closeProps}
          type="button"
          aria-label={intl.formatMessage({ id: 'onboarding.tour.close' })}
          className="-mr-1 -mt-1 shrink-0 rounded-md p-1 text-text-muted transition-colors hover:bg-bg-muted hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 cursor-pointer"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {bodyId && (
        <p className="text-sm leading-relaxed text-text-secondary">
          {intl.formatMessage({ id: bodyId })}
        </p>
      )}

      <div className="mt-4 flex items-center justify-between gap-3">
        <button
          {...skipProps}
          type="button"
          className="text-xs font-medium text-text-muted transition-colors hover:text-text focus-visible:outline-none focus-visible:underline cursor-pointer"
        >
          {intl.formatMessage({ id: 'onboarding.tour.skip' })}
        </button>
        <div className="flex items-center gap-2">
          {index > 0 && (
            <Button {...backProps} variant="secondary" size="sm">
              {intl.formatMessage({ id: 'onboarding.tour.back' })}
            </Button>
          )}
          <Button {...primaryProps} size="sm">
            {isLastStep
              ? intl.formatMessage({ id: 'onboarding.tour.done' })
              : intl.formatMessage({ id: 'onboarding.tour.next' })}
          </Button>
        </div>
      </div>
    </div>
  )
}
