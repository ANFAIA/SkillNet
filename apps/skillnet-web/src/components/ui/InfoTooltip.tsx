import { useState } from 'react'

export interface InfoTooltipProps {
  text: string
}

/** Click-to-toggle tooltip with an (i) icon. */
export function InfoTooltip({ text }: InfoTooltipProps) {
  const [open, setOpen] = useState(false)
  return (
    <span className="relative inline-flex">
      <button
        type="button"
        className="text-text-muted hover:text-primary p-0 ml-1"
        onClick={() => setOpen(!open)}
        onBlur={() => setOpen(false)}
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="16" x2="12" y2="12" />
          <line x1="12" y1="8" x2="12.01" y2="8" />
        </svg>
      </button>
      {open && (
        <span className="absolute left-0 top-6 z-10 w-56 bg-text text-bg text-xs rounded-md px-3 py-2 shadow-md leading-relaxed">
          {text}
        </span>
      )}
    </span>
  )
}
