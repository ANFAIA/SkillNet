import { useEffect, useState } from 'react'
import { Card, CardTitle, Badge, Button, Input, SkeletonRow } from '../../components/ui'
import { useSettings, useUpdateLlmSettings, useTestLlm, useUpdateFeatures } from '../../api/settings'
import { ApiError } from '../../api/client'

export function Settings() {
  const { data: settings, isLoading, error } = useSettings()
  const update = useUpdateLlmSettings()
  const test = useTestLlm()
  const features = useUpdateFeatures()

  const [model, setModel] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [apiKey, setApiKey] = useState('')

  useEffect(() => {
    if (settings) {
      setModel(settings.llm_model ?? '')
      setBaseUrl(settings.llm_base_url ?? '')
    }
  }, [settings])

  const payload = { model: model.trim(), base_url: baseUrl.trim() || undefined, api_key: apiKey.trim() || undefined }
  const canSubmit = !!model.trim()

  return (
    <div className="max-w-2xl">
      <div className="mb-4">
        <h2 className="text-xl font-semibold text-text">Ajustes</h2>
        <p className="text-sm text-text-secondary mt-0.5">Configura el proveedor de IA de la organizacion</p>
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

          <div className="space-y-3">
            <Input
              label="Modelo"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="ej: anthropic/claude-sonnet-4-20250514, deepseek/deepseek-chat"
            />
            <Input
              label="Base URL (opcional)"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="ej: https://api.deepseek.com/v1"
            />
            <Input
              label="API key (opcional, no se muestra despues de guardar)"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-..."
            />
          </div>

          {update.isError && (
            <p className="text-sm text-danger mt-3">
              {update.error instanceof ApiError ? update.error.body.detail : 'No se pudo guardar la configuracion'}
            </p>
          )}
          {update.isSuccess && <p className="text-sm text-accent mt-3">Configuracion guardada.</p>}

          {test.data && (
            <p className={`text-sm mt-3 ${test.data.ok ? 'text-accent' : 'text-danger'}`}>
              {test.data.ok ? `Conexion correcta (${test.data.model ?? model}).` : `Fallo la conexion: ${test.data.detail ?? 'error'}`}
            </p>
          )}

          <div className="flex gap-2 mt-4">
            <Button size="sm" onClick={() => update.mutate(payload)} disabled={!canSubmit || update.isPending}>
              {update.isPending ? 'Guardando...' : 'Guardar'}
            </Button>
            <Button size="sm" variant="secondary" onClick={() => test.mutate(payload)} disabled={!canSubmit || test.isPending}>
              {test.isPending ? 'Probando...' : 'Probar conexion'}
            </Button>
          </div>

          <p className="text-xs text-text-muted mt-4">
            Cualquier proveedor compatible con litellm. El modelo de embeddings debe coincidir con la dimension
            del vector configurada (por defecto 384). Recomendaciones medidas por modelo en{' '}
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
