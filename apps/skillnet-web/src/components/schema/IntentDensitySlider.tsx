import { useIntl } from 'react-intl'

/**
 * `intent_density` (1..5) — how finely the designer cuts the source document into
 * nodes (§11.1). It is read by `POST /schema/propose` when the designer runs, so
 * changing it after a proposal only affects the next one; the copy says that instead
 * of letting the creator believe the existing nodes will move.
 */

/** Module-level table, so it holds message ids and the component formats them. */
export const INTENT_DENSITY_LABEL_KEYS: Record<number, string> = {
  1: 'schema.density.level1',
  2: 'schema.density.level2',
  3: 'schema.density.level3',
  4: 'schema.density.level4',
  5: 'schema.density.level5',
}

export function IntentDensitySlider({
  value,
  onChange,
  disabled = false,
  className = '',
}: {
  value: number
  onChange: (value: number) => void
  disabled?: boolean
  className?: string
}) {
  const intl = useIntl()

  return (
    <div className={className}>
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor="intent-density" className="text-sm font-medium text-text">
          {intl.formatMessage({ id: 'schema.density.label' })}
        </label>
        <span className="text-xs text-text-muted shrink-0">
          {intl.formatMessage({ id: 'schema.density.value' }, { value })}
        </span>
      </div>
      <input
        id="intent-density"
        type="range"
        min={1}
        max={5}
        step={1}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full mt-2 accent-primary disabled:opacity-50 disabled:cursor-not-allowed"
      />
      <p className="text-xs text-text-secondary mt-1">
        {intl.formatMessage({ id: INTENT_DENSITY_LABEL_KEYS[value] })}
      </p>
      <p className="text-xs text-text-muted mt-1">
        {intl.formatMessage({ id: 'schema.density.hint' })}
      </p>
    </div>
  )
}
