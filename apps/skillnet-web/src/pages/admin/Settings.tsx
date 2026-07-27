import { Card, CardTitle, Badge, Button, SkeletonRow } from '../../components/ui'
import { useSettings, useTestLlm, useUpdateFeatures } from '../../api/settings'
import { ApiError } from '../../api/client'

/**
 * Two cards, and the split between them is the point.
 *
 * The provider is **read-only**: it lives in the deployment's `.env`, because SkillNet
 * runs one organization per deployment and the person who owns the API key is the person
 * who deployed it. What stays here is the operational question an admin genuinely has —
 * is the AI configured, and does it answer? — which is worth answering without an SSH
 * session.
 *
 * The feature switches are writable, because how the product behaves is the admin's
 * call, not the deployer's.
 */
export function Settings() {
  const { data: settings, isLoading, error } = useSettings()
  const test = useTestLlm()
  const features = useUpdateFeatures()

  return (
    <div className="max-w-2xl">
      <div className="mb-4">
        <h2 className="text-xl font-semibold text-text">Ajustes</h2>
        <p className="text-sm text-text-secondary mt-0.5">Estado del proveedor de IA y comportamiento del tutor</p>
      </div>

      {isLoading ? (
        <Card><SkeletonRow /></Card>
      ) : error ? (
        <Card><p className="text-sm text-danger">No se pudieron cargar los ajustes.</p></Card>
      ) : (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <CardTitle>Proveedor de IA (LLM)</CardTitle>
            <Badge variant={settings?.llm_configured ? 'accent' : 'warning'} badgeStyle="plain">
              {settings?.llm_configured ? 'Configurado' : 'Sin configurar'}
            </Badge>
          </div>

          <dl className="space-y-2 text-sm">
            <div className="flex gap-3">
              <dt className="text-text-muted w-32 shrink-0">Modelo</dt>
              <dd className="text-text font-mono text-xs break-all min-w-0">
                {settings?.llm_model ?? 'sin configurar'}
              </dd>
            </div>
            <div className="flex gap-3">
              <dt className="text-text-muted w-32 shrink-0">Embeddings</dt>
              <dd className="text-text font-mono text-xs break-all min-w-0">
                {settings?.embedding_model ?? 'sin configurar'}
              </dd>
            </div>
            <div className="flex gap-3">
              <dt className="text-text-muted w-32 shrink-0">Endpoint</dt>
              <dd className="text-text font-mono text-xs break-all min-w-0">
                {settings?.llm_base_url ?? 'el del proveedor'}
              </dd>
            </div>
          </dl>

          {test.data && (
            <p className={`text-sm mt-4 ${test.data.ok ? 'text-accent' : 'text-danger'}`}>
              {test.data.ok
                ? `Conexion correcta (${test.data.model ?? ''}).`
                : `Fallo la conexion: ${test.data.detail ?? 'error'}`}
            </p>
          )}

          <div className="mt-4">
            <Button
              size="sm"
              variant="secondary"
              onClick={() => test.mutate()}
              disabled={test.isPending}
            >
              {test.isPending ? 'Probando...' : 'Probar conexion'}
            </Button>
          </div>

          <p className="text-xs text-text-muted mt-4">
            El proveedor se configura en el <span className="font-mono">.env</span> del
            despliegue (<span className="font-mono">LLM_MODEL</span>,{' '}
            <span className="font-mono">LLM_API_KEY</span>,{' '}
            <span className="font-mono">LLM_BASE_URL</span>), no desde aqui: la clave es de
            quien despliega y paga el proveedor. Vale cualquiera compatible con litellm.
            Numeros medidos por modelo en{' '}
            <span className="font-mono">docs/design/tuning.md</span>.
          </p>
        </Card>
      )}

      {!isLoading && !error && settings && (
        <Card className="mt-4">
          <CardTitle className="mb-1">Respuestas del tutor</CardTitle>
          <p className="text-sm text-text-secondary mb-4">
            Como se presentan las respuestas del chat a los empleados.
          </p>

          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              className="mt-1 accent-primary shrink-0"
              checked={settings.chat_generative_ui}
              disabled={features.isPending}
              onChange={(e) => features.mutate({ chat_generative_ui: e.target.checked })}
            />
            <span className="min-w-0">
              <span className="block text-sm font-medium text-text">
                Maquetar las respuestas con los bloques del curso
              </span>
              <span className="block text-sm text-text-secondary mt-0.5">
                El tutor entrega la respuesta como pasos, tabla o aviso cuando esa es la
                forma que mejor le va, en vez de como texto corrido. Cuesta una llamada
                mas al modelo por respuesta.
              </span>
              <span className="block text-xs text-text-muted mt-1">
                Apagado, el tutor responde en texto. Encendido, si el modelo devuelve algo
                que no vale, la respuesta cae a texto sola: nunca se queda en blanco.
              </span>
            </span>
          </label>

          {features.isError && (
            <p className="text-sm text-danger mt-3">
              {features.error instanceof ApiError
                ? features.error.body.detail
                : 'No se pudo guardar el ajuste'}
            </p>
          )}
        </Card>
      )}
    </div>
  )
}
