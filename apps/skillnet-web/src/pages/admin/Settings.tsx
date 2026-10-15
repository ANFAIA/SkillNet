import { useIntl } from 'react-intl'
import { PageHeader, Select, SkeletonRow, Switch } from '../../components/ui'
import { AppearanceSettings } from '../../components/settings/AppearanceSettings'
import { CapabilityHealthBanner } from '../../components/settings/CapabilityHealthBanner'
import { LearningPreferencesSection } from '../../components/settings/LearningPreferencesSection'
import { AccountSection } from '../../components/settings/AccountSection'
import { BugReportEntry, BugReportsAdminEntry } from '../../components/settings/BugReportEntry'
import { SettingRow } from '../../components/settings/SettingRow'
import { useWorkspaceMode } from '../../hooks/useAuth'
import { useSettings, useUpdateFeatures } from '../../api/settings'
import { apiErrorMessage } from '../../lib/apiErrors'
import { usePreferences } from '../../stores/preferences'
import type { Locale } from '../../stores/preferences'
import type { OrgSettings } from '../../types'

/**
 * What the admin can actually change, and nothing else.
 *
 * The AI provider used to be shown here. It is gone: it lives in the deployment's
 * `.env`, so an admin could read it but never act on it, and a model id on screen is
 * noise to the person running the training. When something fails to generate the error
 * now says why — in the moment, where it happens, which beats a page you have to
 * remember to visit.
 *
 * What survives from that card is one line, and only when it earns itself: a warning if
 * no model is configured at all. That is the single case where this screen tells the
 * admin something they could not otherwise find out — nothing works, and nothing else
 * explains why.
 */

export function Settings() {
  const intl = useIntl()
  const { data: settings, isLoading, error } = useSettings()
  const features = useUpdateFeatures()

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title={intl.formatMessage({ id: 'settings.title' })} />

      {isLoading ? (
        <div className="py-5">
          <SkeletonRow />
        </div>
      ) : error ? (
        <p className="text-sm text-danger py-5">{intl.formatMessage({ id: 'settings.loadError' })}</p>
      ) : settings ? (
        <SettingsBody settings={settings} features={features} />
      ) : null}
    </div>
  )
}

function SettingsBody({
  settings,
  features,
}: {
  settings: OrgSettings
  features: ReturnType<typeof useUpdateFeatures>
}) {
  const intl = useIntl()
  const workspaceMode = useWorkspaceMode()
  const locale = usePreferences((s) => s.locale)
  const setLocale = usePreferences((s) => s.setLocale)

  return (
    <>
      {/* Consolidated, dismissible health notice: what is degraded and why
          (docs/design/degraded-mode-ux.md §1). Replaces the old model-only warning —
          the `!ai` line covers the "no model configured" case and adds voice / images. */}
      <CapabilityHealthBanner />

      <div className="mt-4 space-y-8">
        <AppearanceSettings />

        <div>
        {/* Language selector */}
        <SettingRow
          title={intl.formatMessage({ id: 'settings.language' })}
        >
          <Select
            label={intl.formatMessage({ id: 'settings.language' })}
            hideLabel
            value={locale}
            onChange={(e) => setLocale(e.target.value as Locale)}
            className="w-36"
          >
            <option value="es">{intl.formatMessage({ id: 'settings.langEs' })}</option>
            <option value="en">{intl.formatMessage({ id: 'settings.langEn' })}</option>
          </Select>
        </SettingRow>

        {/* Generative UI toggle */}
        <SettingRow
          title={intl.formatMessage({ id: 'settings.chatGenUi' })}
          description={intl.formatMessage({ id: 'settings.chatGenUiDesc' })}
        >
          <Switch
            checked={settings.chat_generative_ui}
            disabled={features.isPending}
            onCheckedChange={(next) => features.mutate({ chat_generative_ui: next })}
            label={intl.formatMessage({ id: 'settings.chatGenUi' })}
          />
        </SettingRow>

        {/* Share bug reports with the SkillNet team. Off by default: a report leaves this
            deployment only because the admin chose it. */}
        <SettingRow
          title={intl.formatMessage({ id: 'settings.shareBugs' })}
          description={intl.formatMessage({ id: 'settings.shareBugsDesc' })}
        >
          <Switch
            checked={settings.share_bug_reports}
            disabled={features.isPending}
            onCheckedChange={(next) =>
              features.mutate({
                chat_generative_ui: settings.chat_generative_ui,
                share_bug_reports: next,
              })
            }
            label={intl.formatMessage({ id: 'settings.shareBugs' })}
          />
        </SettingRow>

        <BugReportEntry />
        <BugReportsAdminEntry />
        </div>

        <div>
          <h2 className="text-sm font-semibold text-text mb-1">
            {intl.formatMessage({ id: 'account.title' })}
          </h2>
          <AccountSection />
        </div>
      </div>

      {features.isError && (
        <p className="text-sm text-danger mt-3">
          {apiErrorMessage(intl, features.error, 'settings.saveError')}
        </p>
      )}

      {/* The individual-mode owner also learns, so their personalization lives
          here alongside the deployment settings — the same form the employee has,
          minus the theme block (already shown above). See audience-modes.md. */}
      {workspaceMode === 'individual' && (
        <div className="mt-8 border-t border-border pt-6">
          <h2 className="text-base font-semibold text-text mb-4">
            {intl.formatMessage({ id: 'learningPreferences.title' })}
          </h2>
          <LearningPreferencesSection showAppearance={false} />
        </div>
      )}

    </>
  )
}
