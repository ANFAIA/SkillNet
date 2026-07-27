/**
 * `intent_density` (1..5) — how finely the designer cuts the source document into
 * nodes (§11.1). It is read by `POST /schema/propose` when the designer runs, so
 * changing it after a proposal only affects the next one; the copy says that instead
 * of letting the creator believe the existing nodes will move.
 */

export const INTENT_DENSITY_LABELS: Record<number, string> = {
  1: 'Muy pocos nodos, cada uno muy amplio',
  2: 'Pocos nodos, tramos largos',
  3: 'Equilibrado',
  4: 'Muchos nodos, tramos cortos',
  5: 'Maxima granularidad, casi una idea por nodo',
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
  return (
    <div className={className}>
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor="intent-density" className="text-sm font-medium text-text">
          Densidad de intencion
        </label>
        <span className="text-xs text-text-muted shrink-0">{value} de 5</span>
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
      <p className="text-xs text-text-secondary mt-1">{INTENT_DENSITY_LABELS[value]}</p>
      <p className="text-xs text-text-muted mt-1">
        Solo afecta a la proxima propuesta. Los nodos que ya existen no se mueven.
      </p>
    </div>
  )
}
