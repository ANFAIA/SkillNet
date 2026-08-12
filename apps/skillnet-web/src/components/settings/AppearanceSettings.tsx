import { useIntl } from 'react-intl'
import { useTheme } from '../../hooks/useTheme'
import { ACCENT_COLOR_OPTIONS } from '../../lib/accent-themes'
import type { Theme } from '../../stores/preferences'
import { SegmentedControl } from './SegmentedControl'
import { SettingsIcon } from './SettingsIcon'

type AppearanceIconProps = {
  size?: number
  className?: string
}

function CheckIcon({ size = 16, className }: AppearanceIconProps) {
  return (
    <svg aria-hidden="true" className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="m5 12 4 4L19 6" />
    </svg>
  )
}

function PipetteIcon({ size = 16, className }: AppearanceIconProps) {
  return (
    <svg aria-hidden="true" className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m19 3 2 2-9.5 9.5-3-3L18 2a1.4 1.4 0 0 1 2 0l1 1a1.4 1.4 0 0 1 0 2" />
      <path d="m9 13-6 6v2h2l6-6" />
    </svg>
  )
}

export function AppearanceSettings({
  className = '',
  embedded = false,
  compact = false,
}: {
  className?: string
  embedded?: boolean
  compact?: boolean
}) {
  const intl = useIntl()
  const {
    theme,
    setTheme,
    accentColor,
    customAccent,
    setAccentColor,
    setCustomAccent,
  } = useTheme()
  const colorModes = [
    { value: 'light' as Theme, label: intl.formatMessage({ id: 'settings.themeLight' }), icon: <SettingsIcon name="sun" size={15} /> },
    { value: 'dark' as Theme, label: intl.formatMessage({ id: 'settings.themeDark' }), icon: <SettingsIcon name="moon" size={15} /> },
    { value: 'system' as Theme, label: intl.formatMessage({ id: 'settings.themeSystem' }), icon: <SettingsIcon name="monitor" size={15} /> },
  ]

  return (
    <section className={`${embedded ? '' : 'border border-border rounded-xl p-5'} ${className}`}>
      <div className="flex items-center gap-2 text-text">
        {compact && <SettingsIcon name="palette" size={16} className="text-text-muted" />}
        <h2 className="text-base font-semibold">
          {intl.formatMessage({ id: 'appearance.title' })}
        </h2>
      </div>

      <div className={compact ? 'mt-4 grid grid-cols-[repeat(auto-fit,minmax(min(100%,20rem),1fr))] gap-5' : ''}>
      <fieldset className={compact ? '' : 'mt-5'}>
        <legend className="text-sm font-medium text-text">
          {intl.formatMessage({ id: 'appearance.colorMode' })}
        </legend>
        <SegmentedControl
          value={theme}
          options={colorModes}
          onChange={setTheme}
          label={intl.formatMessage({ id: 'appearance.colorMode' })}
          layoutId="appearance-color-mode"
          className="mt-3 max-w-xl"
        />
      </fieldset>

      <fieldset className={compact ? '' : 'mt-6'}>
        <legend className="text-sm font-medium text-text">
          {intl.formatMessage({ id: 'appearance.accentColor' })}
        </legend>

        <div role="radiogroup" className="mt-3 flex flex-wrap items-center gap-3">
          {ACCENT_COLOR_OPTIONS.map((option) => {
            const selected = accentColor === option.value
            return (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={selected}
                aria-label={intl.formatMessage({ id: option.labelId })}
                data-accent-swatch={option.value}
                onClick={() => setAccentColor(option.value)}
                className={`appearance-accent-swatch grid size-8 place-items-center rounded-full border-2 border-bg cursor-pointer transition-transform duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 ${selected ? 'ring-2 ring-offset-2 ring-offset-bg ring-primary scale-105' : 'hover:scale-105'}`}
              >
                {selected && <CheckIcon size={14} className="text-white" />}
              </button>
            )
          })}

          <label
            className={`appearance-custom-accent relative grid size-8 shrink-0 place-items-center overflow-hidden rounded-full cursor-pointer transition-transform duration-200 focus-within:ring-2 focus-within:ring-primary/40 ${accentColor === 'custom' ? 'ring-2 ring-offset-2 ring-offset-bg ring-primary scale-105' : 'hover:scale-105'}`}
          >
            <input
              type="color"
              value={customAccent}
              onChange={(event) => setCustomAccent(event.target.value)}
              aria-label={intl.formatMessage({ id: 'appearance.accent.custom' })}
              className="appearance-custom-accent__input absolute inset-0 size-full cursor-pointer"
            />
            <span className="pointer-events-none grid size-5 place-items-center rounded-full bg-white text-zinc-700">
              <PipetteIcon size={11} />
            </span>
          </label>
        </div>
      </fieldset>
      </div>

    </section>
  )
}
