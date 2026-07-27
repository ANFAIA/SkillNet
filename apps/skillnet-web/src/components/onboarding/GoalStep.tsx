import { useState } from 'react'
import { ChoiceList } from './ChoiceList'
import type { OnboardingQuestion } from '../../api/onboarding'

export interface GoalStepProps {
  question: OnboardingQuestion
  value: string
  onChange: (value: string) => void
}

/**
 * Question 2 — "¿Para qué quieres usar SkillNet ahora mismo?" (§6.2).
 *
 * Andragogy: the adult needs the *why* before investing time. `goal` **does not
 * travel to the LLM** (§3.3) — it is consumed deterministically in the client as
 * the opening line of the `lead` block, so the promise this question makes is kept
 * every time instead of whenever the model remembers to write it.
 *
 * "Otro" is free text, so the stored value is either one of the three option values
 * or whatever the learner typed. There is no second piece of state for that: which
 * row is active is derived from whether the value matches a known option.
 */
export function GoalStep({ question, value, onChange }: GoalStepProps) {
  const options = question.options ?? []
  const matchesOption = options.some((option) => option.value === value)
  const [otherActive, setOtherActive] = useState(!matchesOption && value !== '')

  const showOther = question.allow_other === true

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-text">{question.prompt}</h2>

      <ChoiceList
        name="goal"
        options={options}
        value={otherActive ? null : value}
        onSelect={(next) => {
          setOtherActive(false)
          onChange(next)
        }}
      >
        {showOther && (
          <div className="space-y-2">
            <label className="flex items-start gap-3 p-3 rounded-lg border border-border cursor-pointer transition-colors hover:border-primary has-[:checked]:border-primary has-[:checked]:bg-primary-subtle has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-primary/40">
              <input
                type="radio"
                name="goal"
                checked={otherActive}
                onChange={() => {
                  setOtherActive(true)
                  onChange('')
                }}
                className="mt-0.5 accent-primary shrink-0"
              />
              <span className="block text-sm font-medium text-text">Otro</span>
            </label>

            {otherActive && (
              <input
                type="text"
                value={value}
                onChange={(event) => onChange(event.target.value)}
                placeholder="Cuéntanoslo en una línea"
                maxLength={200}
                aria-label="Otro objetivo"
                className="w-full px-3 py-2 text-sm text-text border border-border rounded-lg bg-bg placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors duration-150"
              />
            )}
          </div>
        )}
      </ChoiceList>
    </div>
  )
}
