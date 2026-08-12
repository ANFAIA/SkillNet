interface SwitchProps {
  checked: boolean
  disabled?: boolean
  onCheckedChange: (checked: boolean) => void
  label: string
}

export function Switch({ checked, disabled = false, onCheckedChange, label }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={`relative h-6 w-11 shrink-0 rounded-full transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:cursor-not-allowed disabled:opacity-50 ${checked ? 'bg-primary' : 'bg-border-strong'}`}
    >
      <span className={`absolute left-0.5 top-0.5 size-5 rounded-full bg-white shadow-sm transition-transform duration-200 ${checked ? 'translate-x-5' : 'translate-x-0'}`} />
    </button>
  )
}
