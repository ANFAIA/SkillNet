import { useState } from 'react'

import { DIDACT_LAB_FIXTURES } from '../../lib/didact/lab-fixtures'
import { didactPolicyFor } from '../../lib/didact/policy'
import type { DidactRegistryEntry } from '../../lib/didact/registry-types'
import { DidactLabPreview } from './DidactLabPreview'

export function DidactLabCard({ entry }: { entry: DidactRegistryEntry }) {
  const [open, setOpen] = useState(false)
  const policy = didactPolicyFor(entry.componentId)
  const fixture = DIDACT_LAB_FIXTURES[entry.componentId]

  return (
    <article className="rounded-lg border border-border bg-surface p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-text-muted">
            {entry.registryItem}
          </p>
          <h2 className="mt-1 text-lg font-semibold text-text">{entry.exportName}</h2>
          <code className="text-xs text-text-muted">{entry.componentId}</code>
        </div>
        <span className="rounded-full border border-border px-2.5 py-1 text-xs text-text-muted">
          {entry.maturity}
        </span>
      </div>

      <div className="mt-4 flex flex-wrap gap-2 text-xs">
        <span className="rounded-md bg-bg-muted px-2 py-1">
          {fixture ? 'fixture visual' : 'contrato pendiente'}
        </span>
        <span className="rounded-md bg-bg-muted px-2 py-1">{policy?.fallbackMode}</span>
      </div>

      {policy && policy.requiredPorts.length > 0 ? (
        <p className="mt-3 text-sm text-text-muted">
          Requiere host: {policy.requiredPorts.join(', ')}
        </p>
      ) : null}
      {fixture ? <p className="mt-3 text-sm text-text-muted">{fixture.note}</p> : null}

      <details
        className="mt-4 border-t border-border pt-4"
        onToggle={(event) => setOpen(event.currentTarget.open)}
      >
        <summary className="cursor-pointer text-sm font-medium text-primary">
          Ver implementación
        </summary>
        <div className="mt-4">
          <DidactLabPreview entry={entry} fixture={fixture} load={open} />
        </div>
      </details>
    </article>
  )
}
