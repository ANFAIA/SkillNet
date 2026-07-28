import { SkeletonRow } from '../../components/ui'
import { useSettings, useUpdateFeatures } from '../../api/settings'
import { ApiError } from '../../api/client'
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

function Toggle({
  checked,
  disabled,
  onChange,
  label,
}: {
  checked: boolean
  disabled?: boolean
  onChange: (next: boolean) => void
  label: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative shrink-0 w-11 h-6 rounded-full transition-colors duration-200
        disabled:opacity-50 disabled:cursor-not-allowed
        focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40
        ${checked ? 'bg-primary' : 'bg-border'}`}
    >
      <span
        className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow-sm
          transition-transform duration-200 ${checked ? 'translate-x-5' : 'translate-x-0'}`}
      />
    </button>
  )
}

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
  const { data: settings, isLoading, error } = useSettings()
  const features = useUpdateFeatures()

  return (
    <div>
      <div className="mb-2">
        <h2 className="text-xl font-semibold text-text">Ajustes</h2>
        <p className="text-sm text-text-secondary mt-0.5">
          Como se comporta SkillNet para tu organizacion.
        </p>
      </div>

      {isLoading ? (
        <div className="py-5">
          <SkeletonRow />
        </div>
      ) : error ? (
        <p className="text-sm text-danger py-5">No se pudieron cargar los ajustes.</p>
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
  return (
    <>
      {!settings.llm_configured && (
        <div className="mt-4 rounded-lg border border-warning/40 bg-warning/5 p-3">
          <p className="text-sm text-text">
            No hay ningun modelo de IA configurado, asi que no se puede generar contenido
            ni responder en el chat.
          </p>
          <p className="text-xs text-text-muted mt-1">
            Se configura en el <span className="font-mono">.env</span> del despliegue:{' '}
            <span className="font-mono">LLM_MODEL</span> y{' '}
            <span className="font-mono">LLM_API_KEY</span>.
          </p>
        </div>
      )}

      <div className="mt-2 border-t border-border">
        <SettingRow
          title="Maquetar las respuestas del tutor"
          description="El tutor contesta con pasos, tablas o avisos cuando encajan mejor que un parrafo. Si el modelo no acierta, la respuesta sale en texto."
        >
          <Toggle
            checked={settings.chat_generative_ui}
            disabled={features.isPending}
            onChange={(next) => features.mutate({ chat_generative_ui: next })}
            label="Maquetar las respuestas del tutor"
          />
        </SettingRow>
      </div>

      {features.isError && (
        <p className="text-sm text-danger mt-3">
          {features.error instanceof ApiError
            ? features.error.body.detail
            : 'No se pudo guardar el ajuste'}
        </p>
      )}
    </>
  )
}
