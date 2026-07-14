import type { InputHTMLAttributes } from 'react'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
}

export function Input({
  label,
  error,
  className = '',
  ...props
}: InputProps) {
  return (
    <div className="space-y-1 max-w-full">
      {label && (
        <label className="block text-sm font-medium text-text">
          {label}
        </label>
      )}
      <input
        className={`
          w-full px-3 py-2 text-sm text-text
          border border-border rounded-lg bg-bg
          placeholder:text-text-muted
          focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20
          transition-colors duration-150
          disabled:opacity-50 disabled:cursor-not-allowed
          ${error ? 'border-danger focus:border-danger focus:ring-danger/20' : ''}
          ${className}
        `}
        {...props}
      />
      {error && (
        <p className="text-xs text-danger">{error}</p>
      )}
    </div>
  )
}
