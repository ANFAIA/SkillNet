import type { OnboardingOption } from '../../api/onboarding'

export interface ChoiceListProps {
  /** Radio group name — one per question, so the groups never bleed into each other. */
  name: string
  options: OnboardingOption[]
  /** Currently selected option value, or `null` when the question is unanswered. */
  value: string | null
  onSelect: (value: string) => void
  /** Rendered after the options — question 2's "otro" row lives here. */
  children?: React.ReactNode
}

/**
 * The option rows shared by the three single-choice screens (§6.2, questions 2-4).
 *
 * Real `<input type="radio">` elements, not divs with `role="radio"`: that buys
 * arrow-key navigation inside the group, Space to select, the native focus ring and
 * the group semantics of the surrounding `<fieldset>`/`<legend>` for free. The card
 * look is CSS on the label (`has-[:checked]`), so the accessible control is the one
 * that is actually there.
 */
export function ChoiceList({ name, options, value, onSelect, children }: ChoiceListProps) {
  return (
    <div className="space-y-2">
      {options.map((option) => (
        <label
          key={option.value}
          className="flex items-start gap-3 p-3 rounded-lg border border-border cursor-pointer transition-colors hover:border-primary has-[:checked]:border-primary has-[:checked]:bg-primary-subtle has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-primary/40"
        >
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={value === option.value}
            onChange={() => onSelect(option.value)}
            className="mt-0.5 accent-primary shrink-0"
          />
          <span className="min-w-0">
            <span className="block text-sm font-medium text-text">{option.label}</span>
            {option.hint && (
              <span className="block text-xs text-text-secondary mt-0.5">{option.hint}</span>
            )}
          </span>
        </label>
      ))}
      {children}
    </div>
  )
}
