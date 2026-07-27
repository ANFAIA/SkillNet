import type { TextareaHTMLAttributes } from 'react'

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  hint?: string
  error?: string
}

/**
 * `Input`'s sibling, deliberately identical in every shared class so the two never
 * drift. The only additions are `hint` — a line under the field for the cases where
 * a placeholder is not enough to say what a good answer looks like — and a default
 * `rows` that fits a short paragraph without pushing the form's buttons off screen.
 */
export function Textarea({
  label,
  hint,
  error,
  className = '',
  rows = 5,
  ...props
}: TextareaProps) {
  return (
    <div className="space-y-1 max-w-full">
      {label && <label className="block text-sm font-medium text-text">{label}</label>}
      <textarea
        rows={rows}
        className={`
          w-full px-3 py-2 text-sm text-text
          border border-border rounded-lg bg-bg
          placeholder:text-text-muted
          focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20
          transition-colors duration-150
          disabled:opacity-50 disabled:cursor-not-allowed
          resize-y
          ${error ? 'border-danger focus:border-danger focus:ring-danger/20' : ''}
          ${className}
        `}
        {...props}
      />
      {hint && !error && <p className="text-xs text-text-muted">{hint}</p>}
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  )
}
