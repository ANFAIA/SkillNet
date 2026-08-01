import { useState, useMemo } from 'react'
import { Mafs, Coordinates, Plot, Point, MovablePoint, Text, vec } from 'mafs'
import 'mafs/core.css'
import { BLOCK_TITLE } from './rhythm'

export interface ManipulableGraphBlockProps {
  title: string
  xLabel: string
  yLabel: string
  points: string[][]
  functions: string[]
}

interface ParsedPoint {
  label: string
  x: number
  y: number
  draggable: boolean
}

function parsePoints(raw: string[][]): ParsedPoint[] {
  if (!Array.isArray(raw)) return []
  return raw
    .filter((row) => Array.isArray(row) && row.length >= 3)
    .map((row) => ({
      label: String(row[0] ?? ''),
      x: Number(row[1]) || 0,
      y: Number(row[2]) || 0,
      draggable: row[3] === 'true' || row[3] === '1',
    }))
}

/**
 * Build a function from a math expression string. Only allows a safe subset:
 * Math.*, numbers, operators, parentheses, and the variable x.
 * Returns a no-op (y=0) if the expression is not safe.
 */
function buildFn(expr: string): ((x: number) => number) | null {
  if (typeof expr !== 'string' || !expr.trim()) return null
  // Allow: digits, whitespace, x, Math.*, operators, parens, dots, commas
  if (!/^[\d\s+\-*/().x,a-zA-Z]+$/.test(expr)) return null
  // Must not contain anything besides Math.xxx and x as identifiers
  const sanitized = expr.replace(/Math\.\w+/g, '').replace(/\bx\b/g, '')
  if (/[a-zA-Z]/.test(sanitized)) return null
  try {
    // eslint-disable-next-line no-new-func
    const fn = new Function('x', `"use strict"; return (${expr})`) as (x: number) => number
    // Smoke test
    const test = fn(1)
    if (!Number.isFinite(test)) return null
    return fn
  } catch {
    return null
  }
}

const PLOT_COLORS = [
  'var(--color-primary)',
  'var(--color-accent)',
  'var(--color-warning)',
  'var(--color-danger)',
]

export function ManipulableGraphBlock({
  title,
  xLabel,
  yLabel,
  points: rawPoints,
  functions: rawFunctions,
}: ManipulableGraphBlockProps) {
  const initialPoints = useMemo(() => parsePoints(rawPoints), [rawPoints])
  const [pointPositions, setPointPositions] = useState<Record<number, vec.Vector2>>({})

  const fns = useMemo(() => {
    if (!Array.isArray(rawFunctions)) return []
    return rawFunctions
      .map((expr, idx) => ({ fn: buildFn(String(expr)), idx }))
      .filter((entry): entry is { fn: (x: number) => number; idx: number } => entry.fn !== null)
  }, [rawFunctions])

  function handlePointMove(idx: number, pos: vec.Vector2) {
    setPointPositions((prev) => ({ ...prev, [idx]: pos }))
  }

  return (
    <div className="min-w-0">
      {title ? <p className={BLOCK_TITLE}>{title}</p> : null}

      <div className="border border-border rounded-lg overflow-hidden">
        <Mafs height={300} pan zoom>
          <Coordinates.Cartesian
            xAxis={{ lines: 1, labels: (n) => String(n) }}
            yAxis={{ lines: 1, labels: (n) => String(n) }}
          />

          {/* Functions */}
          {fns.map(({ fn, idx }) => (
            <Plot.OfX
              key={`fn-${idx}`}
              y={fn}
              color={PLOT_COLORS[idx % PLOT_COLORS.length]}
            />
          ))}

          {/* Points */}
          {initialPoints.map((pt, idx) => {
            const pos = pointPositions[idx] ?? [pt.x, pt.y]
            if (pt.draggable) {
              return (
                <MovablePoint
                  key={`pt-${idx}`}
                  point={pos as vec.Vector2}
                  onMove={(newPos) => handlePointMove(idx, newPos)}
                  color="var(--color-primary)"
                />
              )
            }
            return (
              <Point
                key={`pt-${idx}`}
                x={pos[0]}
                y={pos[1]}
                color="var(--color-primary)"
              />
            )
          })}

          {/* Point labels */}
          {initialPoints.map((pt, idx) => {
            const pos = pointPositions[idx] ?? [pt.x, pt.y]
            if (!pt.label) return null
            return (
              <Text
                key={`label-${idx}`}
                x={pos[0]}
                y={pos[1]}
                attach="e"
                attachDistance={15}
                size={12}
              >
                {pt.label}
              </Text>
            )
          })}

          {/* Axis labels */}
          {xLabel ? (
            <Text x={5} y={-0.5} attach="e" size={12}>
              {xLabel}
            </Text>
          ) : null}
          {yLabel ? (
            <Text x={0.5} y={5} attach="n" size={12}>
              {yLabel}
            </Text>
          ) : null}
        </Mafs>
      </div>
    </div>
  )
}
