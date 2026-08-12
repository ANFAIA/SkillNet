import type { InputHTMLAttributes } from 'react'

interface SearchFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label: string
}

export function SearchField({ label, className = '', ...props }: SearchFieldProps) {
  return (
    <label className={`relative block min-w-0 ${className}`}>
      <span className="sr-only">{label}</span>
      <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-muted">
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-4-4" />
      </svg>
      <input
        type="search"
        className="w-full rounded-lg border border-border bg-bg py-2 pl-9 pr-3 text-sm text-text outline-none transition-colors placeholder:text-text-muted focus:border-primary focus:ring-1 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-50"
        {...props}
      />
    </label>
  )
}
