import {
  createElement,
  useEffect,
  useMemo,
  useState,
  type ComponentType,
  type ReactNode,
} from 'react'

import { DidactErrorBoundary } from './DidactErrorBoundary'
import { DidactHostProvider } from './DidactHostContext'
import { DIDACT_COMPONENT_LOADERS, loadDidactExport } from './generated-loaders'
import type { DidactHostPorts } from './host-ports'
import { resolveDidactMount, withoutProtectedAnswerKeys } from './runtime'

type MountMessages = {
  loading: string
  unavailable: string
  failed: string
  degraded: string
}

const DEFAULT_MESSAGES: MountMessages = {
  loading: 'Cargando actividad…',
  unavailable: 'Esta actividad no está disponible en este entorno.',
  failed: 'No se pudo mostrar esta actividad.',
  degraded: 'Algunas funciones de esta actividad no están disponibles.',
}

function StatusMessage({ children, kind }: { children: ReactNode; kind: string }) {
  return (
    <div
      className="rounded-lg border border-border bg-bg-subtle px-4 py-3 text-sm text-text-secondary"
      data-didact-status={kind}
      role={kind === 'failed' ? 'alert' : 'status'}
    >
      {children}
    </div>
  )
}

export function DidactComponentMount({
  componentId,
  componentProps = {},
  ports,
  messages: messageOverrides,
  onError,
}: {
  componentId: string
  componentProps?: Readonly<Record<string, unknown>>
  ports: DidactHostPorts
  messages?: Partial<MountMessages>
  onError?: (error: Error) => void
}) {
  const messages = { ...DEFAULT_MESSAGES, ...messageOverrides }
  const resolution = useMemo(() => resolveDidactMount(componentId, ports), [componentId, ports])
  const [loaded, setLoaded] = useState<ComponentType<Record<string, unknown>> | null>(null)
  const [loadError, setLoadError] = useState<Error | null>(null)

  useEffect(() => {
    let active = true
    setLoaded(null)
    setLoadError(null)

    if (resolution.availability.status === 'blocked' || !(componentId in DIDACT_COMPONENT_LOADERS)) {
      return () => { active = false }
    }

    loadDidactExport(componentId as keyof typeof DIDACT_COMPONENT_LOADERS)
      .then((value) => {
        if (active) setLoaded(() => value as ComponentType<Record<string, unknown>>)
      })
      .catch((error: unknown) => {
        if (!active) return
        const normalized = error instanceof Error ? error : new Error(String(error))
        setLoadError(normalized)
        onError?.(normalized)
      })

    return () => { active = false }
  }, [componentId, onError, resolution.availability.status])

  if (resolution.availability.status === 'blocked') {
    return <StatusMessage kind="blocked">{messages.unavailable}</StatusMessage>
  }
  if (loadError) return <StatusMessage kind="failed">{messages.failed}</StatusMessage>
  if (!loaded) return <StatusMessage kind="loading">{messages.loading}</StatusMessage>

  const safeProps = withoutProtectedAnswerKeys(componentProps) as Record<string, unknown>
  const errorFallback = <StatusMessage kind="failed">{messages.failed}</StatusMessage>

  return (
    <DidactHostProvider ports={ports}>
      <div className="didact-scope" data-didact-availability={resolution.availability.status}>
        {resolution.availability.status === 'degraded' && (
          <p className="sr-only" role="status">{messages.degraded}</p>
        )}
        <DidactErrorBoundary key={componentId} fallback={errorFallback} onError={(error) => onError?.(error)}>
          {createElement(loaded, safeProps)}
        </DidactErrorBoundary>
      </div>
    </DidactHostProvider>
  )
}
