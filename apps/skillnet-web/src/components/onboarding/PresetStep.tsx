import { ChoiceList } from './ChoiceList'
import type { LearningPreset, OnboardingQuestion } from '../../api/onboarding'

export interface PresetStepProps {
  question: OnboardingQuestion
  value: LearningPreset | null
  onChange: (value: LearningPreset) => void
}

/**
 * Question 4 — "¿Cómo prefieres estudiar?" (§6.2).
 *
 * This is **presentation**, not modality: it changes block size and pacing, not what
 * is taught. That is why it is safe to ask and reversible without restrictions — it
 * gives real autonomy where a "learning style" question would give a noisy signal
 * and a promise that does not improve learning (§6.3).
 *
 * The value is mirrored into `users.learning_profile` by the server in the same
 * transaction as the profile row (§11.2).
 */
export function PresetStep({ question, value, onChange }: PresetStepProps) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-text">{question.prompt}</h2>

      <ChoiceList
        name="preset"
        options={question.options ?? []}
        value={value}
        onSelect={(next) => onChange(next as LearningPreset)}
      />
    </div>
  )
}
