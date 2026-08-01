import { useState } from 'react'
import { BLOCK_TITLE, INLINE_SURFACE } from './rhythm'

export interface SliderExplorationBlockProps {
  title: string
  variable: string
  min: number
  max: number
  step: number
  formula: string
  description: string
}

/**
 * Substitute the variable name in a formula string with the current value and
 * attempt a simple arithmetic evaluation. Falls back to string substitution
 * when the expression is too complex to evaluate safely.
 */
function evaluateFormula(formula: string, variable: string, value: number): string {
  // Replace the variable name with the numeric value for display
  const substituted = formula.replace(
    new RegExp(`\\b${variable.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'g'),
    String(value),
  )

  // Try to compute the right-hand side if the formula has "="
  const eqIdx = substituted.lastIndexOf('=')
  if (eqIdx === -1) return substituted

  const lhs = substituted.slice(0, eqIdx).trim()
  const rhs = substituted.slice(eqIdx + 1).trim()

  // Parse simple arithmetic: numbers, +, -, *, /, parentheses, spaces
  if (/^[\d\s+\-*/().]+$/.test(rhs)) {
    try {
      // Safe subset: only digits and arithmetic operators
      const result = Function(`"use strict"; return (${rhs})`)() as number
      if (Number.isFinite(result)) {
        return `${lhs} = ${rhs} = ${Number.isInteger(result) ? result : result.toFixed(2)}`
      }
    } catch {
      // Fall through to plain substitution
    }
  }

  return substituted
}

export function SliderExplorationBlock({
  title,
  variable,
  min,
  max,
  step,
  formula,
  description,
}: SliderExplorationBlockProps) {
  const clampedMin = Number.isFinite(min) ? min : 0
  const clampedMax = Number.isFinite(max) ? max : 100
  const clampedStep = Number.isFinite(step) && step > 0 ? step : 1
  const [value, setValue] = useState(clampedMin)

  const display = formula ? evaluateFormula(formula, variable || 'x', value) : ''

  return (
    <div className={INLINE_SURFACE}>
      {title ? <p className={BLOCK_TITLE}>{title}</p> : null}

      <div className="space-y-4">
        {/* Slider row */}
        <div className="space-y-2">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-sm text-text-secondary font-medium">{variable || 'x'}</span>
            <span className="text-sm font-semibold text-text tabular-nums">{value}</span>
          </div>
          <input
            type="range"
            min={clampedMin}
            max={clampedMax}
            step={clampedStep}
            value={value}
            onChange={(e) => setValue(Number(e.target.value))}
            className="w-full h-1.5 bg-bg-muted rounded-full appearance-none cursor-pointer
              [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4
              [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full
              [&::-webkit-slider-thumb]:bg-primary [&::-webkit-slider-thumb]:shadow-sm
              [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:h-4
              [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-primary
              [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:shadow-sm"
            aria-label={`${variable}: ${value}`}
          />
          <div className="flex justify-between text-xs text-text-muted">
            <span>{clampedMin}</span>
            <span>{clampedMax}</span>
          </div>
        </div>

        {/* Formula result */}
        {display ? (
          <div className="bg-bg-subtle border border-border rounded-lg px-4 py-3">
            <p className="text-sm text-text font-mono">{display}</p>
          </div>
        ) : null}

        {/* Description */}
        {description ? (
          <p className="text-sm text-text-secondary">{description}</p>
        ) : null}
      </div>
    </div>
  )
}
