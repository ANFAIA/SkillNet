import { useIntl } from 'react-intl'
import { PageHeader } from '../../components/ui'
import { LearningPreferencesSection } from '../../components/settings/LearningPreferencesSection'
import { AccountSection } from '../../components/settings/AccountSection'

/**
 * The learner's settings screen. The personalization form itself lives in
 * `LearningPreferencesSection` so the individual-mode owner can edit the same
 * preferences from admin Settings; here it is the whole page, with the theme
 * block on top (`showAppearance`).
 */
export function LearningPreferencesPage() {
  const intl = useIntl()
  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader title={intl.formatMessage({ id: 'learningPreferences.title' })} />
      <div className="mt-6">
        <LearningPreferencesSection showAppearance />
      </div>
      <div className="mt-8 border-t border-border pt-6">
        <h2 className="text-base font-semibold text-text mb-4">
          {intl.formatMessage({ id: 'account.title' })}
        </h2>
        <AccountSection />
      </div>
    </div>
  )
}
