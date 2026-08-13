import { ChoiceList } from './ChoiceList'
import { useIntl } from 'react-intl'
import type {
  ModalityPreference,
  OnboardingQuestion,
} from '../../api/onboarding'

export interface LearningPreferencesStepProps {
  question: OnboardingQuestion
  value: ModalityPreference | null
  onChange: (value: ModalityPreference) => void
}

/** A declared preference, not a learning-style label or a rendering guarantee. */
export function LearningPreferencesStep({
  question,
  value,
  onChange,
}: LearningPreferencesStepProps) {
  const intl = useIntl()
  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-text">{question.prompt}</h2>
      <ChoiceList
        name="learning_preferences"
        options={question.options ?? []}
        value={value}
        onSelect={(next) => onChange(next as ModalityPreference)}
      />
      <p className="text-xs text-text-secondary">
        {intl.formatMessage({ id: 'onboarding.learningPreferencesMix' })}
      </p>
    </div>
  )
}
