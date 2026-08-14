import { useEffect, useRef, useState } from 'react'
import { useIntl } from 'react-intl'
import { ApiError } from '../../api/client'
import { useMe } from '../../api/auth'
import {
  ACCESSIBILITY_KEYS,
  DEFAULT_LEARNING_PREFERENCES,
  NO_ACCESSIBILITY,
  normalizeLearningPreferences,
  useLearnerProfile,
  useUpdateLearnerProfile,
} from '../../api/onboarding'
import type {
  AccessibilitySettings,
  DetailPreference,
  ImagePreference,
  LearningPreferences,
  InteractionPreference,
  CompanionModality,
  WebPresentationPreference,
} from '../../api/onboarding'
import { Button, Card, PageHeader, SkeletonRow } from '../../components/ui'
import { AppearanceSettings } from '../../components/settings/AppearanceSettings'
import { LearningPreferencePreview } from '../../components/settings/LearningPreferencePreview'
import { SegmentedControl } from '../../components/settings/SegmentedControl'
import { SettingsIcon } from '../../components/settings/SettingsIcon'

function normalizeAccessibility(value: Record<string, unknown> | null | undefined) {
  return Object.fromEntries(
    ACCESSIBILITY_KEYS.map((key) => [key, value?.[key] === true]),
  ) as AccessibilitySettings
}

export function LearningPreferencesPage() {
  const intl = useIntl()
  const profile = useLearnerProfile()
  const me = useMe()
  const updateLearning = useUpdateLearnerProfile()
  const updateLearningAsync = updateLearning.mutateAsync
  const [preferences, setPreferences] = useState<LearningPreferences>(
    DEFAULT_LEARNING_PREFERENCES,
  )
  const [accessibility, setAccessibility] = useState<AccessibilitySettings>(NO_ACCESSIBILITY)
  const [hydrated, setHydrated] = useState(false)
  const [saved, setSaved] = useState(false)
  const changeVersion = useRef(0)

  useEffect(() => {
    if (hydrated || !profile.data || !me.data) return
    setPreferences(normalizeLearningPreferences(profile.data.learning_preferences))
    setAccessibility(normalizeAccessibility(me.data.accessibility))
    setHydrated(true)
  }, [hydrated, me.data, profile.data])

  const loading = profile.isLoading || me.isLoading
  const loadError = profile.isError || me.isError || (!loading && (!profile.data || !me.data))
  const pending = updateLearning.isPending
  const saveError = updateLearning.error

  function changePreference<Key extends keyof LearningPreferences>(
    key: Key,
    value: LearningPreferences[Key],
  ) {
    changeVersion.current += 1
    setSaved(false)
    setPreferences((current) => ({ ...current, [key]: value }))
  }

  useEffect(() => {
    if (!hydrated || changeVersion.current === 0) return
    const version = changeVersion.current
    const timeout = window.setTimeout(() => {
      updateLearningAsync({
        learning_preferences: preferences,
        accessibility,
      })
        .then(() => {
          if (changeVersion.current === version) setSaved(true)
        })
        .catch(() => {
          // Mutation state renders the useful server error below.
        })
    }, 500)

    return () => window.clearTimeout(timeout)
  }, [accessibility, hydrated, preferences, updateLearningAsync])

  const webPresentationOptions = [
    { value: 'balanced' as WebPresentationPreference, icon: <SettingsIcon name="balance" size={14} /> },
    { value: 'text' as WebPresentationPreference, icon: <SettingsIcon name="text" size={14} /> },
    { value: 'visual' as WebPresentationPreference, icon: <SettingsIcon name="image" size={14} /> },
    { value: 'data' as WebPresentationPreference, icon: <SettingsIcon name="detail" size={14} /> },
  ].map((option) => ({
    ...option,
    label: intl.formatMessage({ id: `learningPreferences.modality.${option.value}` }),
  }))
  const companionModalities: CompanionModality[] = ['audio', 'video']

  function toggleModality(modality: CompanionModality) {
    const selected = preferences.modalities.includes(modality)
    changePreference(
      'modalities',
      selected
        ? preferences.modalities.filter((item) => item !== modality)
        : [...preferences.modalities, modality],
    )
  }
  const interactionOptions = [
    { value: 'standard' as InteractionPreference, icon: <SettingsIcon name="balance" size={14} /> },
    { value: 'interactive' as InteractionPreference, icon: <SettingsIcon name="pointer" size={14} /> },
  ].map((option) => ({
    ...option,
    label: intl.formatMessage({ id: `learningPreferences.interaction.${option.value}` }),
  }))
  const detailOptions = [
    { value: 'concise' as DetailPreference, icon: <SettingsIcon name="zap" size={14} /> },
    { value: 'standard' as DetailPreference, icon: <SettingsIcon name="normal" size={14} /> },
    { value: 'detailed' as DetailPreference, icon: <SettingsIcon name="layers" size={14} /> },
  ].map((option) => ({
    ...option,
    label: intl.formatMessage({ id: `learningPreferences.detail.${option.value}` }),
  }))
  const imageOptions = [
    { value: 'when_useful' as ImagePreference, icon: <SettingsIcon name="sparkles" size={14} /> },
    { value: 'prefer' as ImagePreference, icon: <SettingsIcon name="imagePlus" size={14} /> },
    { value: 'avoid' as ImagePreference, icon: <SettingsIcon name="imageOff" size={14} /> },
  ].map((option) => ({
    ...option,
    label: intl.formatMessage({ id: `learningPreferences.images.${option.value}` }),
  }))

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title={intl.formatMessage({ id: 'learningPreferences.title' })}
        actions={!loading && !loadError && (pending || saved) ? (
          <span className={`text-xs ${saved ? 'text-success' : 'text-text-muted'}`} role="status">
            {intl.formatMessage({
              id: pending ? 'learningPreferences.saving' : 'learningPreferences.saved',
            })}
          </span>
        ) : undefined}
      />

      <Card className="mt-6 !p-0 overflow-hidden">
        <AppearanceSettings embedded compact className="p-4 sm:p-5" />

        <div className="border-t border-border">
          {loading ? (
            <div className="space-y-3 p-5" aria-label={intl.formatMessage({ id: 'learningPreferences.loading' })}>
              <SkeletonRow />
              <SkeletonRow />
              <SkeletonRow />
            </div>
          ) : loadError ? (
            <div className="p-5">
              <p className="text-sm text-danger">
                {intl.formatMessage({ id: 'learningPreferences.loadError' })}
              </p>
              <Button
                variant="secondary"
                className="mt-4"
                onClick={() => {
                  profile.refetch()
                  me.refetch()
                }}
              >
                {intl.formatMessage({ id: 'learningPreferences.retry' })}
              </Button>
            </div>
          ) : (
            <>
              <section className="p-5">
                <div className="mb-4 flex items-center gap-2 text-text">
                  <SettingsIcon name="sparkles" size={16} className="text-text-muted" />
                  <h2 className="text-base font-semibold">
                    {intl.formatMessage({ id: 'learningPreferences.learningStyle' })}
                  </h2>
                </div>

                <div className="grid items-stretch gap-4 lg:grid-cols-[minmax(0,1.65fr)_minmax(15.5rem,0.85fr)]">
                  <div className="grid grid-rows-5 overflow-hidden rounded-lg border border-border bg-surface">
                    <fieldset className="flex min-h-0 flex-col justify-center gap-3 p-4">
                      <legend className="sr-only">
                        {intl.formatMessage({ id: 'learningPreferences.webPresentation' })}
                      </legend>
                      <div className="flex items-center gap-2 text-sm font-medium text-text">
                        <SettingsIcon name="format" size={15} className="text-text-muted" />
                        {intl.formatMessage({ id: 'learningPreferences.webPresentation' })}
                      </div>
                      <SegmentedControl
                        value={preferences.web_presentation}
                        options={webPresentationOptions}
                        onChange={(value) => changePreference('web_presentation', value)}
                        label={intl.formatMessage({ id: 'learningPreferences.webPresentation' })}
                        layoutId="learning-modality"
                      />
                    </fieldset>

                    <fieldset className="flex min-h-0 flex-col justify-center gap-3 border-t border-border p-4">
                      <legend className="sr-only">
                        {intl.formatMessage({ id: 'learningPreferences.companionModalities' })}
                      </legend>
                      <div className="flex items-center gap-2 text-sm font-medium text-text">
                        <SettingsIcon name="format" size={15} className="text-text-muted" />
                        {intl.formatMessage({ id: 'learningPreferences.companionModalities' })}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {companionModalities.map((modality) => (
                          <button
                            key={modality}
                            type="button"
                            aria-pressed={preferences.modalities.includes(modality)}
                            onClick={() => toggleModality(modality)}
                            className={`rounded-md border px-3 py-2 text-sm transition-colors ${
                              preferences.modalities.includes(modality)
                                ? 'border-primary bg-primary-subtle text-primary'
                                : 'border-border text-text-secondary hover:bg-bg-muted'
                            }`}
                          >
                            {intl.formatMessage({ id: `learningPreferences.companion.${modality}` })}
                          </button>
                        ))}
                      </div>
                      <p className="text-xs text-text-muted">
                        {intl.formatMessage({ id: 'learningPreferences.audioDeployment' })}
                      </p>
                    </fieldset>

                    <fieldset className="flex min-h-0 flex-col justify-center gap-3 border-t border-border p-4">
                      <legend className="sr-only">
                        {intl.formatMessage({ id: 'learningPreferences.interaction' })}
                      </legend>
                      <div className="flex items-center gap-2 text-sm font-medium text-text">
                        <SettingsIcon name="pointer" size={15} className="text-text-muted" />
                        {intl.formatMessage({ id: 'learningPreferences.interaction' })}
                      </div>
                      <SegmentedControl
                        value={preferences.interaction}
                        options={interactionOptions}
                        onChange={(value) => changePreference('interaction', value)}
                        label={intl.formatMessage({ id: 'learningPreferences.interaction' })}
                        layoutId="learning-interaction"
                      />
                    </fieldset>

                    <fieldset className="flex min-h-0 flex-col justify-center gap-3 border-t border-border p-4">
                      <legend className="sr-only">
                        {intl.formatMessage({ id: 'learningPreferences.detail' })}
                      </legend>
                      <div className="flex items-center gap-2 text-sm font-medium text-text">
                        <SettingsIcon name="detail" size={15} className="text-text-muted" />
                        {intl.formatMessage({ id: 'learningPreferences.detail' })}
                      </div>
                      <SegmentedControl
                        value={preferences.detail}
                        options={detailOptions}
                        onChange={(value) => changePreference('detail', value)}
                        label={intl.formatMessage({ id: 'learningPreferences.detail' })}
                        layoutId="learning-detail"
                      />
                    </fieldset>

                    <fieldset className="flex min-h-0 flex-col justify-center gap-3 border-t border-border p-4">
                      <legend className="sr-only">
                        {intl.formatMessage({ id: 'learningPreferences.images' })}
                      </legend>
                      <div className="flex items-center gap-2 text-sm font-medium text-text">
                        <SettingsIcon name="images" size={15} className="text-text-muted" />
                        {intl.formatMessage({ id: 'learningPreferences.images' })}
                      </div>
                      <SegmentedControl
                        value={preferences.images}
                        options={imageOptions}
                        onChange={(value) => changePreference('images', value)}
                        label={intl.formatMessage({ id: 'learningPreferences.images' })}
                        layoutId="learning-images"
                      />
                    </fieldset>
                  </div>

                  <LearningPreferencePreview
                    presentation={
                      preferences.interaction === 'interactive'
                        ? 'interactive'
                        : preferences.web_presentation === 'visual'
                          ? 'visual'
                          : preferences.web_presentation === 'text'
                            ? 'textual'
                            : 'balanced'
                    }
                    detail={preferences.detail}
                    images={preferences.images}
                  />
                </div>
              </section>

              <section className="border-t border-border p-5">
                <div className="flex items-center gap-2 text-text">
                  <SettingsIcon name="accessibility" size={16} className="text-text-muted" />
                  <h2 className="text-base font-semibold">
                    {intl.formatMessage({ id: 'learningPreferences.accessibility' })}
                  </h2>
                </div>
                <div className="mt-4 grid gap-x-6 sm:grid-cols-2">
                  {ACCESSIBILITY_KEYS.map((key) => (
                    <label key={key} className="flex min-h-11 cursor-pointer items-center justify-between gap-3 border-b border-border py-3">
                      <span className="text-sm text-text">
                        {intl.formatMessage({ id: `learningPreferences.accessibility.${key}` })}
                      </span>
                      <input
                        type="checkbox"
                        checked={accessibility[key]}
                        onChange={(event) => {
                          changeVersion.current += 1
                          setSaved(false)
                          setAccessibility((current) => ({ ...current, [key]: event.target.checked }))
                        }}
                        className="size-4 shrink-0 accent-primary"
                      />
                    </label>
                  ))}
                </div>
              </section>
            </>
          )}
        </div>
      </Card>

      {saveError && (
        <p className="mt-4 text-sm text-danger" role="alert">
          {saveError instanceof ApiError
            ? saveError.body.detail
            : intl.formatMessage({ id: 'learningPreferences.saveError' })}
        </p>
      )}
    </div>
  )
}
