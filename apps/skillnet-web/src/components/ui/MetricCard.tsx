type MetricColor = 'blue' | 'green' | 'orange' | 'purple'

export interface MetricCardProps {
  value: string
  label: string
  icon: React.ReactNode
  color: MetricColor
  className?: string
}

const colorClasses: Record<MetricColor, string> = {
  blue: 'bg-metric-blue',
  green: 'bg-metric-green',
  orange: 'bg-metric-orange',
  purple: 'bg-metric-purple',
}

function CobwebSvg() {
  return (
    <svg
      width="90"
      height="90"
      viewBox="0 0 90 90"
      fill="none"
      className="absolute top-0 right-0"
      style={{ opacity: 0.18 }}
      aria-hidden="true"
    >
      {/* 5 radial lines from top-right corner */}
      <line x1="90" y1="0" x2="0" y2="0" stroke="white" strokeWidth="1" />
      <line x1="90" y1="0" x2="0" y2="45" stroke="white" strokeWidth="1" />
      <line x1="90" y1="0" x2="0" y2="90" stroke="white" strokeWidth="1" />
      <line x1="90" y1="0" x2="45" y2="90" stroke="white" strokeWidth="1" />
      <line x1="90" y1="0" x2="90" y2="90" stroke="white" strokeWidth="1" />
      {/* Concentric quarter-circle arcs */}
      <path d="M 90 20 A 20 20 0 0 1 70 0" stroke="white" strokeWidth="1" fill="none" />
      <path d="M 90 40 A 40 40 0 0 1 50 0" stroke="white" strokeWidth="1" fill="none" />
      <path d="M 90 60 A 60 60 0 0 1 30 0" stroke="white" strokeWidth="1" fill="none" />
      <path d="M 90 80 A 80 80 0 0 1 10 0" stroke="white" strokeWidth="1" fill="none" />
    </svg>
  )
}

export function MetricCard({ value, label, icon, color, className = '' }: MetricCardProps) {
  return (
    <div
      className={`relative overflow-hidden rounded-xl p-5 ${colorClasses[color]} ${className}`}
    >
      <CobwebSvg />
      <div className="relative z-10">
        <div className="mb-3 text-white/80">
          {icon}
        </div>
        <p className="text-2xl font-semibold text-white">{value}</p>
        <p className="text-sm text-white/80 mt-0.5">{label}</p>
      </div>
    </div>
  )
}
