import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import { duration, ease } from '../../lib/motion'

export type SegmentedOption<Value extends string> = {
  value: Value
  label: string
  icon?: ReactNode
}

export function SegmentedControl<Value extends string>({
  value,
  options,
  onChange,
  label,
  layoutId,
  className = '',
}: {
  value: Value
  options: SegmentedOption<Value>[]
  onChange: (value: Value) => void
  label: string
  layoutId: string
  className?: string
}) {
  const columns =
    options.length === 4 ? 'grid-cols-4' : options.length === 2 ? 'grid-cols-2' : 'grid-cols-3'

  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={`grid w-full ${columns} rounded-xl border border-border bg-bg-subtle p-1 ${className}`}
    >
      {options.map((option) => {
        const selected = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(option.value)}
            className={`relative isolate flex min-w-0 items-center justify-center gap-1 rounded-lg px-1 py-2 text-xs cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 sm:gap-2 sm:px-2 sm:text-sm ${selected ? 'text-white' : 'text-text-secondary hover:text-text'}`}
          >
            {selected && (
              <motion.span
                layoutId={layoutId}
                className="absolute inset-0 -z-10 rounded-lg bg-primary"
                transition={{ duration: duration.fast, ease: ease.base }}
              />
            )}
            {option.icon && <span className="hidden shrink-0 sm:inline-flex">{option.icon}</span>}
            <span className="truncate">{option.label}</span>
          </button>
        )
      })}
    </div>
  )
}
