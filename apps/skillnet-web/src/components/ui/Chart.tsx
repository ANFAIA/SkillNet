import type { CSSProperties, ReactElement } from 'react'
import { ResponsiveContainer } from 'recharts'

export type ChartConfig = Record<string, {
  label: string
  color: string
}>

type ChartContainerProps = {
  config: ChartConfig
  children: ReactElement
  className?: string
  'aria-label': string
}
export function ChartContainer({ config, children, className = '', 'aria-label': ariaLabel }: ChartContainerProps) {
  const colorVariables = Object.fromEntries(
    Object.entries(config).map(([key, item]) => [`--color-${key}`, item.color]),
  ) as CSSProperties

  return (
    <div
      data-chart="chart"
      role="img"
      aria-label={ariaLabel}
      className={`w-full text-xs [&_.recharts-cartesian-axis-tick_text]:fill-text-muted [&_.recharts-cartesian-grid_line]:stroke-border [&_.recharts-curve.recharts-tooltip-cursor]:stroke-border [&_.recharts-sector:focus]:outline-none [&_.recharts-surface]:outline-none ${className}`}
      style={colorVariables}
    >
      <ResponsiveContainer>{children}</ResponsiveContainer>
    </div>
  )
}
