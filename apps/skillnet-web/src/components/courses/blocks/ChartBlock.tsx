import { useEffect, useState } from 'react'
import { BLOCK_TITLE } from './rhythm'
import { ClickableText } from '../ClickableText'
import type { ChartKind } from '../kit/schemas'

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
const VIEW_H = 140
const PAD_X = 4
const PAD_Y = 16
const GRID_LINES = 4

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
 *
 * Visual improvements: taller bars with rounded ends and a gradient fill from
 * primary to primary/70 for depth.
 */
function BarChart({ points }: { points: Array<{ label: string; value: number }> }) {
  const maxAbs = points.reduce((acc, p) => Math.max(acc, Math.abs(p.value)), 0)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true))
    return () => cancelAnimationFrame(id)
  }, [])

  return (
    <ul className="space-y-3 min-w-0">
      {points.map((point, idx) => {
        const pct = maxAbs === 0 ? 0 : Math.max(0, Math.min(100, (point.value / maxAbs) * 100))
        return (
          <li key={idx} className="min-w-0">
            <div className="flex items-baseline justify-between gap-3 mb-1.5">
              <span className="text-xs text-text-secondary truncate">{point.label}</span>
              <span className="text-xs font-semibold text-text tabular-nums shrink-0">
                {formatValue(point.value)}
              </span>
            </div>
            <div className="h-2.5 w-full rounded-full bg-bg-muted overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: mounted ? `${pct}%` : '0%',
                  transition: 'width 0.6s ease',
                  background: 'linear-gradient(90deg, var(--color-primary), var(--color-primary) 60%, color-mix(in srgb, var(--color-primary) 70%, transparent))',
                }}
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
 *
 * Visual improvements: area fill under the line (gradient to transparent),
 * larger dots, value labels above points, and subtle horizontal grid lines.
 */
function LineChart({
  points,
  title,
}: {
  points: Array<{ label: string; value: number }>
  title: string
}) {
  const [dashOffset, setDashOffset] = useState<number | null>(null)

  useEffect(() => {
    // Trigger the draw-on animation after mount
    requestAnimationFrame(() => setDashOffset(0))
  }, [])

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

  // Total polyline length for stroke-dasharray draw animation
  const totalLength = coords.reduce((acc, c, i) => {
    if (i === 0) return 0
    const dx = c.x - coords[i - 1].x
    const dy = c.y - coords[i - 1].y
    return acc + Math.sqrt(dx * dx + dy * dy)
  }, 0)

  // Build the area fill path: line path + close down to baseline + back
  const baseline = VIEW_H - PAD_Y
  const areaPath =
    coords.length > 1
      ? `M${coords[0].x.toFixed(1)},${coords[0].y.toFixed(1)} ` +
        coords
          .slice(1)
          .map(({ x, y }) => `L${x.toFixed(1)},${y.toFixed(1)}`)
          .join(' ') +
        ` L${coords[coords.length - 1].x.toFixed(1)},${baseline} L${coords[0].x.toFixed(1)},${baseline} Z`
      : ''

  // Unique ID for the gradient defs (safe for multiple charts on the page)
  const gradId = `area-grad-${title?.replace(/\W/g, '') || 'chart'}`

  return (
    <div className="min-w-0">
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`${title}. ${summary}`}
        className="w-full h-32 block"
      >
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-primary)" stopOpacity={0.2} />
            <stop offset="100%" stopColor="var(--color-primary)" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        {/* Horizontal grid lines */}
        {Array.from({ length: GRID_LINES }).map((_, i) => {
          const y = PAD_Y + (usableH / GRID_LINES) * i
          return (
            <line
              key={i}
              x1={PAD_X}
              y1={y}
              x2={VIEW_W - PAD_X}
              y2={y}
              stroke="var(--color-border)"
              strokeWidth={0.5}
              strokeDasharray="4 3"
            />
          )
        })}
        {/* Baseline axis */}
        <line
          x1={PAD_X}
          y1={baseline}
          x2={VIEW_W - PAD_X}
          y2={baseline}
          stroke="var(--color-border-strong)"
          strokeWidth={1}
        />
        {/* Area fill */}
        {areaPath && <path d={areaPath} fill={`url(#${gradId})`} />}
        {/* Line */}
        {coords.length > 1 && (
          <polyline
            points={polyline}
            fill="none"
            className="stroke-primary"
            strokeWidth={2.5}
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
            strokeDasharray={totalLength}
            strokeDashoffset={dashOffset === null ? totalLength : 0}
            style={{ transition: 'stroke-dashoffset 0.8s ease' }}
          />
        )}
        {/* Dots — larger for visibility, with white center ring */}
        {coords.map(({ x, y }, idx) => (
          <g key={idx}>
            <circle cx={x} cy={y} r={4.5} className="fill-bg" />
            <circle cx={x} cy={y} r={3.5} className="fill-primary" />
          </g>
        ))}
        {/* Value labels above each point */}
        {coords.map(({ x, y }, idx) => (
          <text
            key={`val-${idx}`}
            x={x}
            y={y - 8}
            textAnchor="middle"
            className="fill-text-secondary"
            style={{ fontSize: '8px', fontWeight: 500 }}
          >
            {formatValue(points[idx].value)}
          </text>
        ))}
      </svg>
      <div className="flex justify-between gap-2 mt-1.5">
        {points.map((point, idx) => (
          <span key={idx} className="text-xs text-text-muted truncate">
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
        <ClickableText as="p" className={BLOCK_TITLE}>{title}</ClickableText>
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
