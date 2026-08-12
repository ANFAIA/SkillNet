import { useEffect, useState } from 'react'
import { useIntl } from 'react-intl'
import { ApiError } from '../../api/client'
import { useMe } from '../../api/auth'
import {
  ACCESSIBILITY_KEYS,
  DEFAULT_LEARNING_PREFERENCES,
  NO_ACCESSIBILITY,
  useLearnerProfile,
  useUpdateLearnerProfile,
} from '../../api/onboarding'
import type {
  AccessibilitySettings,
  DetailPreference,
  ImagePreference,
  LearningPreferences,
  PresentationPreference,
} from '../../api/onboarding'
import { Button, Card, SkeletonRow } from '../../components/ui'

type Choice = { value: string; label: string; hint: string }

function RadioChoices({
  name,
  value,
  options,
  onChange,
}: {
  name: string
  value: string
  options: Choice[]
  onChange: (value: string) => void
}) {
  return (
    <div className="grid gap-2 sm:grid-cols-3">
      {options.map((option) => (
        <label
          key={option.value}
          className="flex items-start gap-3 rounded-lg border border-border p-3 cursor-pointer hover:border-primary has-[:checked]:border-primary has-[:checked]:bg-primary-subtle has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-primary/40"
        >
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={value === option.value}
            onChange={() => onChange(option.value)}
            className="mt-0.5 accent-primary shrink-0"
          />
          <span className="min-w-0">
            <span className="block text-sm font-medium text-text">{option.label}</span>
            <span className="block text-xs text-text-secondary mt-0.5">{option.hint}</span>
          </span>
        </label>
      ))}
    </div>
  )
}

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
  const [preferences, setPreferences] = useState<LearningPreferences>(
    DEFAULT_LEARNING_PREFERENCES,
  )
  const [accessibility, setAccessibility] = useState<AccessibilitySettings>(NO_ACCESSIBILITY)
  const [hydrated, setHydrated] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (hydrated || !profile.data || !me.data) return
    setPreferences(profile.data.learning_preferences ?? DEFAULT_LEARNING_PREFERENCES)
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
    setSaved(false)
    setPreferences((current) => ({ ...current, [key]: value }))
  }

  async function save() {
    setSaved(false)
    try {
      await updateLearning.mutateAsync({
        learning_preferences: preferences,
        accessibility,
      })
      setSaved(true)
    } catch {
      // Mutation state renders the useful server error below.
    }
  }

  const presentationOptions: Choice[] = [
    ['balanced', 'Balanced', 'Mix explanations, visuals and practice.'],
    ['visual', 'Visual', 'Prioritise diagrams and images when they help.'],
    ['textual', 'Textual', 'Prioritise clear written explanations.'],
    ['interactive', 'Interactive', 'Prioritise practice and exploration.'],
  ].map(([value, fallbackLabel, fallbackHint]) => ({
    value,
    label: intl.formatMessage(
      { id: `learningPreferences.presentation.${value}` },
      { fallback: fallbackLabel },
    ),
    hint: intl.formatMessage(
      { id: `learningPreferences.presentation.${value}.hint` },
      { fallback: fallbackHint },
    ),
  }))
  const detailOptions: Choice[] = ['concise', 'standard', 'detailed'].map((value) => ({
    value,
    label: intl.formatMessage({ id: `learningPreferences.detail.${value}` }),
    hint: intl.formatMessage({ id: `learningPreferences.detail.${value}.hint` }),
  }))
  const imageOptions: Choice[] = ['when_useful', 'prefer', 'avoid'].map((value) => ({
    value,
    label: intl.formatMessage({ id: `learningPreferences.images.${value}` }),
    hint: intl.formatMessage({ id: `learningPreferences.images.${value}.hint` }),
  }))

  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-xl font-semibold text-text">
        {intl.formatMessage({ id: 'learningPreferences.title' })}
      </h1>
      <p className="text-sm text-text-secondary mt-1">
        {intl.formatMessage({ id: 'learningPreferences.subtitle' })}
      </p>

      {loading ? (
        <div className="mt-6 space-y-3" aria-label={intl.formatMessage({ id: 'learningPreferences.loading' })}>
          <SkeletonRow />
          <SkeletonRow />
          <SkeletonRow />
        </div>
      ) : loadError ? (
        <Card className="mt-6">
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
        </Card>
      ) : (
        <div className="mt-6 space-y-4">
          <Card>
            <fieldset>
              <legend className="text-base font-medium text-text">
                {intl.formatMessage({ id: 'learningPreferences.presentation' })}
              </legend>
              <p className="text-sm text-text-secondary mt-1 mb-4">
                {intl.formatMessage({ id: 'learningPreferences.presentationDesc' })}
              </p>
              <RadioChoices
                name="presentation"
                value={preferences.presentation}
                options={presentationOptions}
                onChange={(value) => changePreference('presentation', value as PresentationPreference)}
              />
            </fieldset>
          </Card>

          <Card>
            <fieldset>
              <legend className="text-base font-medium text-text">
                {intl.formatMessage({ id: 'learningPreferences.detail' })}
              </legend>
              <p className="text-sm text-text-secondary mt-1 mb-4">
                {intl.formatMessage({ id: 'learningPreferences.detailDesc' })}
              </p>
              <RadioChoices
                name="detail"
                value={preferences.detail}
                options={detailOptions}
                onChange={(value) => changePreference('detail', value as DetailPreference)}
              />
            </fieldset>
          </Card>

          <Card>
            <fieldset>
              <legend className="text-base font-medium text-text">
                {intl.formatMessage({ id: 'learningPreferences.images' })}
              </legend>
              <p className="text-sm text-text-secondary mt-1 mb-4">
                {intl.formatMessage({ id: 'learningPreferences.imagesDesc' })}
              </p>
              <RadioChoices
                name="images"
                value={preferences.images}
                options={imageOptions}
                onChange={(value) => changePreference('images', value as ImagePreference)}
              />
            </fieldset>
          </Card>

          <Card>
            <fieldset>
              <legend className="text-base font-medium text-text">
                {intl.formatMessage({ id: 'learningPreferences.accessibility' })}
              </legend>
              <p className="text-sm text-text-secondary mt-1 mb-4">
                {intl.formatMessage({ id: 'learningPreferences.accessibilityDesc' })}
              </p>
              <div className="grid gap-2 sm:grid-cols-2">
                {ACCESSIBILITY_KEYS.map((key) => (
                  <label key={key} className="flex items-center gap-3 rounded-lg border border-border p-3 cursor-pointer hover:border-primary has-[:checked]:border-primary has-[:checked]:bg-primary-subtle">
                    <input
                      type="checkbox"
                      checked={accessibility[key]}
                      onChange={(event) => {
                        setSaved(false)
                        setAccessibility((current) => ({ ...current, [key]: event.target.checked }))
                      }}
                      className="accent-primary"
                    />
                    <span className="text-sm text-text">
                      {intl.formatMessage({ id: `learningPreferences.accessibility.${key}` })}
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
          </Card>

          <p className="text-sm text-text-secondary">
            {intl.formatMessage({ id: 'learningPreferences.mixNote' })}
          </p>
          {saveError && (
            <p className="text-sm text-danger" role="alert">
              {saveError instanceof ApiError
                ? saveError.body.detail
                : intl.formatMessage({ id: 'learningPreferences.saveError' })}
            </p>
          )}
          {saved && (
            <p className="text-sm text-success" role="status">
              {intl.formatMessage({ id: 'learningPreferences.saved' })}
            </p>
          )}
          <Button onClick={save} disabled={pending}>
            {intl.formatMessage({
              id: pending ? 'learningPreferences.saving' : 'learningPreferences.save',
            })}
          </Button>
        </div>
      )}
    </div>
  )
}
