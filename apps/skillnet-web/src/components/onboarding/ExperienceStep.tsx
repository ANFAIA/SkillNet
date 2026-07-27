import { ChoiceList } from './ChoiceList'
import type { ExperienceLevel, OnboardingQuestion } from '../../api/onboarding'

export interface ExperienceStepProps {
  question: OnboardingQuestion
  value: ExperienceLevel | null
  onChange: (value: ExperienceLevel) => void
}

/**
 * Question 3 — "¿Cuánta experiencia tienes en tu puesto actual?" (§6.2).
 *
 * Prior knowledge is the one adaptation dimension with a large effect size, and it
 * *inverts* the instructional design: worked examples help the novice and actively
 * hurt the expert. Hence the question exists at all, while "preferred format" does
 * not (§6.3, d≈0.04).
 *
 * The question deliberately **names no course**: the field is one per person and
 * feeds the `cache_key` of *all* their courses, so asking about one topic and
 * applying the answer to another would be incoherent. Per-competence granularity
 * comes from `user_skills` via the pre-assessment, not from this declaration.
 *
 * Answering "Ninguna" here is a real declaration and stores `'none'`. Not answering
 * is not: skipping stores `'unknown'`, which the client never sends (§6.1).
 */
export function ExperienceStep({ question, value, onChange }: ExperienceStepProps) {
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-text">{question.prompt}</h2>

      <ChoiceList
        name="experience_level"
        options={question.options ?? []}
        value={value}
        onSelect={(next) => onChange(next as ExperienceLevel)}
      />
    </div>
  )
}
