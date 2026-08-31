import { useIntl } from 'react-intl'
import { isAccessibilityKey } from '../../api/onboarding'
import type { AccessibilityKey, AccessibilitySettings, OnboardingQuestion } from '../../api/onboarding'

export interface AccessibilityStepProps {
  question: OnboardingQuestion
  value: AccessibilitySettings
  onToggle: (key: AccessibilityKey, enabled: boolean) => void
}

/**
 * Question 5 — "¿Quieres activar algún ajuste de lectura?" (§6.2). Optional.
 *
 * It asks about **reading needs**, never about conditions. A diagnosis is
 * special-category health data (art. 9 RGPD) and buys nothing: these four concrete
 * settings produce the same functional result without the legal risk, and without
 * putting a label on anyone (§6.3).
 *
 * There is no "read aloud": there is no TTS in this PR and no audio component in the
 * frozen kit, and offering an accommodation that does not exist is worse than not
 * offering it (§6.2). The wizard renders only the options the server sends, and
 * filters them to the four keys `users.accessibility` accepts — so an option the
 * product cannot honour cannot appear here even if a future response lists one.
 */
export function AccessibilityStep({ question, value, onToggle }: AccessibilityStepProps) {
  const intl = useIntl()
  const options = (question.options ?? []).filter((option) => isAccessibilityKey(option.value))

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-text">{question.prompt}</h2>

      <div className="space-y-2">
        {options.map((option) => {
          const key = option.value as AccessibilityKey
          return (
            <label
              key={key}
              className="flex items-start gap-3 p-3 rounded-lg border border-border cursor-pointer transition-colors hover:border-primary has-[:checked]:border-primary has-[:checked]:bg-primary-subtle has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-primary/40"
            >
              <input
                type="checkbox"
                checked={value[key]}
                onChange={(event) => onToggle(key, event.target.checked)}
                className="mt-0.5 accent-primary shrink-0"
              />
              <span className="block text-sm font-medium text-text">{option.label}</span>
            </label>
          )
        })}
      </div>

      <p className="text-xs text-text-secondary">
        {intl.formatMessage({ id: 'onboarding.accessibility.optionalNote' })}
      </p>
    </div>
  )
}
