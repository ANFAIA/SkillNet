import { useEffect, useState } from 'react'

import { ErrorBoundary } from '../ErrorBoundary'
import { loadDidactExport } from '../../lib/didact/generated-loaders'
import type { DidactRegistryEntry } from '../../lib/didact/registry-types'
import { asLabComponent, type DidactLabFixture } from '../../lib/didact/lab-fixtures'

type Props = {
  entry: DidactRegistryEntry
  fixture?: DidactLabFixture
  load: boolean
}

export function DidactLabPreview({ entry, fixture, load }: Props) {
  const [component, setComponent] = useState<unknown>()
  const [verified, setVerified] = useState(false)
  const [error, setError] = useState<string>()

  useEffect(() => {
    if (!load || component || verified || error) return
    let active = true
    void loadDidactExport(entry.componentId)
      .then((value) => {
        if (!active) return
        if (fixture) {
          // React treats a function passed directly to a state setter as an updater and
          // would execute the Didact component with undefined props.
          setComponent(() => value)
        } else {
          // Verify the real export without ever retaining or mounting it.
          setVerified(true)
        }
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : String(reason))
      })
    return () => {
      active = false
    }
  }, [component, entry.componentId, error, fixture, load, verified])

  if (!load) return <p className="text-sm text-text-muted">Abre el detalle para cargar el módulo real.</p>
  if (error) return <p role="alert" className="text-sm text-danger">{error}</p>
  if (!fixture) {
    if (!verified) return <div className="h-20 animate-pulse rounded-md bg-bg-muted" />
    return (
      <div className="rounded-md border border-dashed border-border px-4 py-5 text-sm text-text-muted">
        Módulo y export cargados correctamente. No se monta sin sus puertos y datos protegidos.
      </div>
    )
  }

  if (!component) return <div className="h-20 animate-pulse rounded-md bg-bg-muted" />

  const Component = asLabComponent(component)
  return (
    <ErrorBoundary
      fallback={(renderError, reset) => (
        <div role="alert" className="rounded-md border border-danger/30 p-4 text-sm">
          <p className="font-medium text-danger">Este fixture falló sin afectar a la galería.</p>
          <p className="mt-1 text-text-muted">{renderError.message}</p>
          <button type="button" className="mt-3 text-primary" onClick={reset}>Reintentar</button>
        </div>
      )}
    >
      <div className="didact-scope rounded-md border border-border bg-surface p-4">
        <Component {...fixture.props} />
      </div>
    </ErrorBoundary>
  )
}
