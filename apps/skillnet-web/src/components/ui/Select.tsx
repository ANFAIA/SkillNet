import type { SelectHTMLAttributes } from 'react'

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string
  hideLabel?: boolean
}

function ChevronDown() {
  return (
    <svg
      aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-text-muted"
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}

export function Select({ label, hideLabel = false, className = '', children, ...props }: SelectProps) {
  return (
    <label className={`block min-w-0 text-sm font-medium text-text ${className}`}>
      <span className={hideLabel ? 'sr-only' : 'mb-1.5 block'}>{label}</span>
      <div className="relative">
        <select
          className="w-full appearance-none rounded-lg border border-border bg-bg py-2 pl-3 pr-8 text-sm text-text outline-none transition-colors focus:border-primary focus:ring-1 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-50"
          {...props}
        >
          {children}
        </select>
        <ChevronDown />
      </div>
    </label>
  )
}
