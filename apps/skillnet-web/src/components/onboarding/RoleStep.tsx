import { Input } from '../ui'
import type { OnboardingQuestion } from '../../api/onboarding'

export interface RoleStepProps {
  question: OnboardingQuestion
  /** RGPD art. 13 notice from `OnboardingRead.notice` — never client copy (§3.3). */
  notice: string
  value: string
  onChange: (value: string) => void
}

/**
 * Question 1 — "¿Cuál es tu puesto?" (§6.2).
 *
 * Free text with the six sector suggestions the server sends. Free text and not a
 * closed list because `role_title` goes **literally** into the `genera_ui` system
 * prompt: a wrong-but-close pick from a dropdown ("Operario" for a forklift driver)
 * degrades every example the learner will ever see, and no list covers an SME.
 *
 * The notice sits directly under the question at body size and body colour, not as
 * fine print: §3.3 requires it at the point of collection with the same visual
 * weight as the question, because this is the screen where the data that leaves for
 * the LLM provider is typed in.
 */
export function RoleStep({ question, notice, value, onChange }: RoleStepProps) {
  const suggestions = question.suggestions ?? []

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-text">{question.prompt}</h2>

      <div className="space-y-3">
        <Input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Escribe tu puesto"
          maxLength={120}
          autoComplete="organization-title"
          aria-label={question.prompt}
          aria-describedby="onboarding-notice"
        />

        {suggestions.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {suggestions.map((suggestion) => {
              const selected = value === suggestion
              return (
                <button
                  key={suggestion}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => onChange(suggestion)}
                  className={`px-3 py-1 rounded-md border text-xs transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 ${
                    selected
                      ? 'border-primary bg-primary-subtle text-primary'
                      : 'border-border text-text-secondary hover:border-primary'
                  }`}
                >
                  {suggestion}
                </button>
              )
            })}
          </div>
        )}
      </div>

      <p id="onboarding-notice" className="text-sm text-text">
        {notice}
      </p>
    </div>
  )
}
