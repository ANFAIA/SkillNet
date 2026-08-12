import { useMemo, useState } from 'react'

import { DidactLabCard } from '../../components/didact/DidactLabCard'
import { DIDACT_COMPONENT_REGISTRY } from '../../lib/didact/generated-registry'
import { DIDACT_LAB_FIXTURES } from '../../lib/didact/lab-fixtures'

export function DidactLab() {
  const [query, setQuery] = useState('')
  const visible = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    if (!normalized) return DIDACT_COMPONENT_REGISTRY
    return DIDACT_COMPONENT_REGISTRY.filter((entry) =>
      `${entry.componentId} ${entry.exportName} ${entry.registryItem}`.toLowerCase().includes(normalized),
    )
  }, [query])

  return (
    <main className="min-h-screen bg-bg px-6 py-8 text-text lg:px-10">
      <div className="mx-auto max-w-7xl">
        <header className="max-w-3xl">
          <p className="text-sm font-medium text-primary">Laboratorio interno</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight">Didact: 34 tipos disponibles</h1>
          <p className="mt-3 text-text-muted">
            Galería de QA del snapshot vendorizado. Abrir un detalle carga solamente su módulo.
            Los componentes con puertos obligatorios no reciben respuestas ni estado inventados.
          </p>
        </header>

        <div className="mt-8 flex flex-wrap items-center gap-4">
          <label className="min-w-64 flex-1">
            <span className="sr-only">Buscar componente</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Buscar por tipo, export o módulo…"
              className="h-11 w-full rounded-md border border-border bg-surface px-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
            />
          </label>
          <p className="text-sm text-text-muted">
            {visible.length} visibles · {Object.keys(DIDACT_LAB_FIXTURES).length} fixtures controlados
          </p>
        </div>

        <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {visible.map((entry) => <DidactLabCard key={entry.componentId} entry={entry} />)}
        </section>
      </div>
    </main>
  )
}
