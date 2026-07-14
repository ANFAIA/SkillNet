type SkillLevel = 'low' | 'medium' | 'high' | 'expert'

export interface SkillBarsProps {
  level: SkillLevel
  className?: string
}

/** Bar x-centers and heights within the 25x18 viewBox (bottom-aligned) */
const bars = [
  { x: 2, h: 6 },
  { x: 9, h: 10 },
  { x: 16, h: 14 },
  { x: 23, h: 17 },
] as const

const levelConfig: Record<SkillLevel, { count: number; color: string }> = {
  low:    { count: 1, color: 'var(--color-skill-low)' },
  medium: { count: 2, color: 'var(--color-skill-medium)' },
  high:   { count: 3, color: 'var(--color-skill-high)' },
  expert: { count: 4, color: 'var(--color-primary)' },
}

const inactiveColor = 'var(--color-skill-none)'

export function SkillBars({ level, className = '' }: SkillBarsProps) {
  const { count, color } = levelConfig[level]

  /* Build a curved "web thread" path connecting the tops of active bars */
  const activeBarTops = bars.slice(0, count).map(b => ({ x: b.x, y: 18 - b.h }))
  let threadPath = ''
  if (activeBarTops.length >= 2) {
    threadPath = `M ${activeBarTops[0].x} ${activeBarTops[0].y}`
    for (let i = 1; i < activeBarTops.length; i++) {
      const prev = activeBarTops[i - 1]
      const curr = activeBarTops[i]
      const cpX = (prev.x + curr.x) / 2
      const cpY = Math.min(prev.y, curr.y) - 2
      threadPath += ` Q ${cpX} ${cpY} ${curr.x} ${curr.y}`
    }
  }

  return (
    <svg
      width="25"
      height="18"
      viewBox="0 0 25 18"
      className={`shrink-0 ${className}`}
      aria-label={`Skill level: ${level}`}
      role="img"
    >
      {/* Bars */}
      {bars.map((b, i) => (
        <rect
          key={i}
          x={b.x - 2}
          y={18 - b.h}
          width={4}
          height={b.h}
          rx={1}
          fill={i < count ? color : inactiveColor}
        />
      ))}
      {/* Web thread connecting active bar tops */}
      {threadPath && (
        <path
          d={threadPath}
          stroke={color}
          strokeWidth="1"
          fill="none"
          opacity="0.55"
        />
      )}
    </svg>
  )
}
