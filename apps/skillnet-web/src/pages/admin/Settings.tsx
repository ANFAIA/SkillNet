import { useIntl } from 'react-intl'
import { PageHeader, Select, SkeletonRow, Switch } from '../../components/ui'
import { AppearanceSettings } from '../../components/settings/AppearanceSettings'
import { LearningPreferencesSection } from '../../components/settings/LearningPreferencesSection'
import { useWorkspaceMode } from '../../hooks/useAuth'
import { useSettings, useUpdateFeatures } from '../../api/settings'
import { ApiError } from '../../api/client'
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

function SettingRow({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-start justify-between gap-6 py-5 border-b border-border">
      <div className="min-w-0">
        <p className="text-sm font-medium text-text">{title}</p>
        <p className="text-sm text-text-secondary mt-1">{description}</p>
      </div>
      {children}
    </div>
  )
}

export function Settings() {
  const intl = useIntl()
  const { data: settings, isLoading, error } = useSettings()
  const features = useUpdateFeatures()

  return (
    <div>
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
      {!settings.llm_configured && (
        <div className="mt-4 rounded-lg border border-warning/40 bg-warning/5 p-3">
          <p className="text-sm text-text">
            {intl.formatMessage({ id: 'settings.noModel' })}
          </p>
          <p className="text-xs text-text-muted mt-1">
            {intl.formatMessage({ id: 'settings.noModelHint' })}
          </p>
        </div>
      )}

      <AppearanceSettings className="mt-4" />

      <div className="mt-6 border-t border-border">
        {/* Language selector */}
        <SettingRow
          title={intl.formatMessage({ id: 'settings.language' })}
          description={intl.formatMessage({ id: 'settings.languageDesc' })}
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
      </div>

      {features.isError && (
        <p className="text-sm text-danger mt-3">
          {features.error instanceof ApiError
            ? features.error.body.detail
            : intl.formatMessage({ id: 'settings.saveError' })}
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
