import { useId, type InputHTMLAttributes } from 'react'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
}

export function Input({
  label,
  error,
  className = '',
  id,
  ...props
}: InputProps) {
  // No `htmlFor`/`id` pairing here previously — the label and input were
  // visually together but not programmatically associated, which breaks
  // screen readers and `getByLabelText` alike. `useId` gives every instance
  // a stable, unique id even when several inputs on the page share a label
  // (e.g. more than one "Current password" field), which a fixed string id
  // would not have.
  const generatedId = useId()
  const inputId = id ?? generatedId

  return (
    <div className="space-y-1 max-w-full">
      {label && (
        <label htmlFor={inputId} className="block text-sm font-medium text-text">
          {label}
        </label>
      )}
      <input
        id={inputId}
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
