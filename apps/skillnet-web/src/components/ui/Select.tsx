import type { SelectHTMLAttributes } from 'react'

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string
  hideLabel?: boolean
}

export function Select({ label, hideLabel = false, className = '', children, ...props }: SelectProps) {
  return (
    <label className={`block min-w-0 text-sm font-medium text-text ${className}`}>
      <span className={hideLabel ? 'sr-only' : 'mb-1.5 block'}>{label}</span>
      <select
        className="w-full rounded-lg border border-border bg-bg px-3 py-2 text-sm text-text outline-none transition-colors focus:border-primary focus:ring-1 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-50"
        {...props}
      >
        {children}
      </select>
    </label>
  )
}
