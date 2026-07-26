import type { ChartKind } from '../../../types/ui-spec'

export interface ChartBlockProps {
  kind: ChartKind
  title: string
  labels: string[]
  values: number[]
}

// Hand-rolled on purpose: no Chart.js, no Recharts. AGENTS.md forbids new
// dependencies without a justification, and two chart kinds with 2-8 points do
// not justify 40 kB of runtime.

const VIEW_W = 320
const VIEW_H = 120
const PAD_X = 4
const PAD_Y = 8

function formatValue(value: number): string {
  return Number.isFinite(value) ? value.toLocaleString('es-ES') : '-'
}

/** Pairs labels with values, dropping the tail of whichever array is longer. */
function toPoints(labels: unknown, values: unknown): Array<{ label: string; value: number }> {
  const labelList = Array.isArray(labels) ? labels : []
  const valueList = Array.isArray(values) ? values : []
  const count = Math.min(labelList.length, valueList.length)
  const points: Array<{ label: string; value: number }> = []
  for (let i = 0; i < count; i += 1) {
    const raw = Number(valueList[i])
    points.push({ label: String(labelList[i] ?? ''), value: Number.isFinite(raw) ? raw : 0 })
  }
  return points
}

/**
 * Horizontal bars. Chosen over vertical bars because the labels are Spanish
 * sentences ("Devoluciones fuera de plazo"), and vertical bars force either
 * rotated text or truncation. Label + number are real text, so the chart is
 * readable by a screen reader with no parallel description.
 */
function BarChart({ points }: { points: Array<{ label: string; value: number }> }) {
  const maxAbs = points.reduce((acc, p) => Math.max(acc, Math.abs(p.value)), 0)

  return (
    <ul className="space-y-2.5 min-w-0">
      {points.map((point, idx) => {
        const pct = maxAbs === 0 ? 0 : Math.max(0, Math.min(100, (point.value / maxAbs) * 100))
        return (
          <li key={idx} className="min-w-0">
            <div className="flex items-baseline justify-between gap-3 mb-1">
              <span className="text-xs text-text-secondary truncate">{point.label}</span>
              <span className="text-xs font-medium text-text tabular-nums shrink-0">
                {formatValue(point.value)}
              </span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-bg-muted overflow-hidden">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${pct}%` }}
              />
            </div>
          </li>
        )
      })}
    </ul>
  )
}

/**
 * Line chart as an inline SVG polyline. `role="img"` plus the `sr-only` value
 * list below is the accessible pair — an SVG alone announces nothing useful.
 */
function LineChart({
  points,
  title,
}: {
  points: Array<{ label: string; value: number }>
  title: string
}) {
  const values = points.map((p) => p.value)
  const max = Math.max(...values, 0)
  const min = Math.min(...values, 0)
  const span = max - min || 1
  const usableW = VIEW_W - PAD_X * 2
  const usableH = VIEW_H - PAD_Y * 2

  const coords = points.map((point, idx) => {
    const x = points.length === 1 ? VIEW_W / 2 : PAD_X + (idx / (points.length - 1)) * usableW
    const y = PAD_Y + usableH - ((point.value - min) / span) * usableH
    return { x, y }
  })

  const polyline = coords.map(({ x, y }) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const summary = points.map((p) => `${p.label}: ${formatValue(p.value)}`).join('; ')

  return (
    <div className="min-w-0">
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`${title}. ${summary}`}
        className="w-full h-28 block"
      >
        <line
          x1={PAD_X}
          y1={VIEW_H - PAD_Y}
          x2={VIEW_W - PAD_X}
          y2={VIEW_H - PAD_Y}
          className="stroke-border"
          strokeWidth={1}
        />
        {coords.length > 1 && (
          <polyline
            points={polyline}
            fill="none"
            className="stroke-primary"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        )}
        {coords.map(({ x, y }, idx) => (
          <circle key={idx} cx={x} cy={y} r={2.5} className="fill-primary" />
        ))}
      </svg>
      <div className="flex justify-between gap-2 mt-1.5">
        {points.map((point, idx) => (
          <span key={idx} className="text-[11px] text-text-muted truncate">
            {point.label}
          </span>
        ))}
      </div>
      <ul className="sr-only">
        {points.map((point, idx) => (
          <li key={idx}>{`${point.label}: ${formatValue(point.value)}`}</li>
        ))}
      </ul>
    </div>
  )
}

export function ChartBlock({ kind, title, labels, values }: ChartBlockProps) {
  const points = toPoints(labels, values)

  return (
    <figure className="min-w-0 m-0">
      {title ? (
        <figcaption className="text-sm font-medium text-text mb-3">{title}</figcaption>
      ) : null}
      {points.length === 0 ? (
        <p className="text-xs text-text-muted">Sin datos para representar.</p>
      ) : kind === 'line' ? (
        <LineChart points={points} title={title} />
      ) : (
        <BarChart points={points} />
      )}
    </figure>
  )
}
