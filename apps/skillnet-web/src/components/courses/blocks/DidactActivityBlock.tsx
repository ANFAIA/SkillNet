import { useEffect, useMemo, useRef } from 'react'

import { useActivityDefinition } from '../../../api/activities'
import { createActivityHostPorts } from '../../../api/activity-ports'
import {
  DidactComponentMount,
  useOptionalDidactHost,
  validatePublicActivityDefinition,
} from '../../../lib/didact'
import type { DidactHostPorts } from '../../../lib/didact'
import { evaluationProps } from './didact-evaluation-adapter'
import {
  SecureEvaluatedActivity,
} from './SecureEvaluatedActivity'
import { usesSecureEvaluationAdapter } from './secure-evaluation-components'
import { AssetBackedDidactActivity } from './AssetBackedDidactActivity'
import { HostProgressActivity } from './HostProgressActivity'

const ASSET_BACKED_COMPONENTS = new Set([
  'didact.hotspot',
  'didact.label-diagram',
  'didact.interactive-media',
])

const HOST_PROGRESS_COMPONENTS = new Set(['didact.progress', 'didact.mastery-badge'])

const ASYNC_EVALUATION_ADAPTERS = new Set([
  'didact.drawing-response',
  'didact.equation-workbench',
  'didact.evidence-annotation',
  'didact.measurement-lab',
])

function honestPorts(componentId: string, ports: DidactHostPorts): DidactHostPorts {
  return {
    persistence: ports.persistence,
    clock: ports.clock,
    events: ports.events,
    ...(ASSET_BACKED_COMPONENTS.has(componentId) ? { assets: ports.assets } : {}),
    ...(ASYNC_EVALUATION_ADAPTERS.has(componentId)
      || usesSecureEvaluationAdapter(componentId)
      || componentId === 'didact.hotspot'
      || componentId === 'didact.label-diagram'
      ? { evaluation: ports.evaluation }
      : {}),
    ...(HOST_PROGRESS_COMPONENTS.has(componentId) ? { progress: ports.progress } : {}),
  }
}

function ActivityStatus({ kind, children }: { kind: string; children: string }) {
  return (
    <div
      className="rounded-lg border border-border bg-bg-subtle px-4 py-3 text-sm text-text-secondary"
      data-didact-activity-status={kind}
      role={kind === 'failed' ? 'alert' : 'status'}
    >
      {children}
    </div>
  )
}

function MountedActivity({
  activityId,
  componentId,
  componentProps,
  ports,
}: {
  activityId: string
  componentId: string
  componentProps: Readonly<Record<string, unknown>>
  ports: DidactHostPorts
}) {
  const startedEventId = useRef(crypto.randomUUID())

  useEffect(() => {
    void ports.events?.emit({
      version: 1,
      eventId: startedEventId.current,
      activityId,
      type: 'started',
      occurredAt: new Date().toISOString(),
      scope: { organizationId: '', courseId: '' },
      componentId,
      payload: {},
    }).catch(() => undefined)
  }, [activityId, componentId, ports.events])

  return <DidactComponentMount componentId={componentId} componentProps={componentProps} ports={ports} />
}

/**
 * The single OpenUI adapter for the complete Didact registry.
 *
 * OpenUI supplies only an opaque activity id and a reviewed component id. The
 * authored definition is fetched from SkillNet and checked before lazy mounting.
 */
export function DidactActivityBlock({
  activityId,
  componentId,
}: {
  activityId: string
  componentId: string
}) {
  const outerPorts = useOptionalDidactHost()
  const httpPorts = useMemo(() => createActivityHostPorts(activityId), [activityId])
  const ports = honestPorts(componentId, { ...httpPorts, ...outerPorts })
  const definition = useActivityDefinition(activityId)

  if (!activityId || !componentId.startsWith('didact.')) {
    return <ActivityStatus kind="failed">La referencia de esta actividad no es válida.</ActivityStatus>
  }
  if (definition.isPending) return <ActivityStatus kind="loading">Cargando actividad…</ActivityStatus>
  if (definition.isError) {
    return <ActivityStatus kind="failed">No se pudo cargar la actividad.</ActivityStatus>
  }

  const validated = validatePublicActivityDefinition(definition.data, activityId, componentId)
  if (!validated.ok) {
    if (validated.reason === 'declined') {
      return <ActivityStatus kind="blocked">Esta actividad no puede ejecutarse con los datos disponibles.</ActivityStatus>
    }
    return <ActivityStatus kind="failed">La definición pública de la actividad no es válida.</ActivityStatus>
  }

  if (usesSecureEvaluationAdapter(componentId)) {
    return (
      <SecureEvaluatedActivity
        activityId={activityId}
        componentId={componentId}
        componentProps={validated.componentProps}
        ports={ports}
      />
    )
  }

  if (ASSET_BACKED_COMPONENTS.has(componentId)) {
    return (
      <AssetBackedDidactActivity
        activityId={activityId}
        componentId={componentId}
        componentProps={validated.componentProps}
        ports={ports}
      />
    )
  }

  if (HOST_PROGRESS_COMPONENTS.has(componentId)) {
    return (
      <HostProgressActivity
        activityId={activityId}
        componentId={componentId}
        componentProps={validated.componentProps}
        ports={ports}
      />
    )
  }

  return (
    <MountedActivity
      activityId={activityId}
      componentId={componentId}
      componentProps={{
        ...validated.componentProps,
        ...evaluationProps(activityId, componentId, ports),
      }}
      ports={ports}
    />
  )
}
