import { useEffect, useMemo, useState, type ReactNode } from 'react'

import {
  DidactComponentMount,
  type AssetReference,
  type DidactHostPorts,
  type DidactValue,
} from '../../../lib/didact'

type Props = Readonly<Record<string, unknown>>

function Status({ kind, children }: { kind: string; children: string }) {
  return <div role={kind === 'failed' ? 'alert' : 'status'} data-didact-asset-status={kind}>{children}</div>
}

function EmbeddedCheckpoint({
  authoring,
  complete,
}: {
  authoring: Record<string, unknown>
  complete: () => void
}) {
  const prompt = typeof authoring.prompt === 'string'
    ? authoring.prompt
    : typeof authoring.question === 'string'
      ? authoring.question
      : 'Revisa este punto de aprendizaje.'
  return (
    <div className="space-y-3">
      <p>{prompt}</p>
      <button type="button" className="rounded-lg border border-border px-3 py-2" onClick={complete}>
        Marcar como revisado
      </button>
    </div>
  )
}

export function AssetBackedDidactActivity({
  activityId,
  componentId,
  componentProps,
  ports,
}: {
  activityId: string
  componentId: string
  componentProps: Props
  ports: DidactHostPorts
}) {
  const assetRef = typeof componentProps.assetRef === 'string' ? componentProps.assetRef : ''
  const [asset, setAsset] = useState<AssetReference>()
  const [failed, setFailed] = useState(false)
  const [state, setState] = useState<DidactValue>()

  useEffect(() => {
    const controller = new AbortController()
    setAsset(undefined)
    setFailed(false)
    if (!assetRef || !ports.assets) {
      setFailed(true)
      return () => controller.abort()
    }
    void ports.assets.resolve(assetRef, { organizationId: '', courseId: '' }, controller.signal)
      .then(setAsset)
      .catch(() => setFailed(true))
    return () => controller.abort()
  }, [assetRef, ports.assets])

  useEffect(() => {
    if (componentId !== 'didact.interactive-media') return
    void ports.persistence?.load(
      { organizationId: '', courseId: '' },
      `interactive-media:${activityId}`,
    ).then(setState).catch(() => undefined)
  }, [activityId, componentId, ports.persistence])

  const mountedProps = useMemo((): Record<string, unknown> => {
    if (!asset) return {}
    const media: ReactNode = (
      <img
        src={asset.url}
        alt=""
        width={asset.width}
        height={asset.height}
        loading="lazy"
        decoding="async"
        className="h-auto w-full object-contain"
      />
    )
    if (componentId === 'didact.hotspot') {
      return {
        ...componentProps,
        media,
        alt: asset.alt,
        longDescription: asset.longDescription ?? componentProps.longDescription,
        onSubmit: (payload: { value: DidactValue }) => {
          void ports.evaluation?.evaluate({
            scope: { organizationId: '', courseId: '' },
            componentId,
            attemptId: crypto.randomUUID(),
            response: payload.value,
          })
        },
      }
    }
    if (componentId === 'didact.label-diagram') {
      return {
        ...componentProps,
        media,
        alt: asset.alt,
        longDescription: asset.longDescription ?? componentProps.longDescription,
        onSubmit: (result: { value: DidactValue }) => {
          void ports.evaluation?.evaluate({
            scope: { organizationId: '', courseId: '' },
            componentId,
            attemptId: crypto.randomUUID(),
            response: result.value,
          })
        },
      }
    }
    const rawDefinition = componentProps.definition
    const definition = rawDefinition && typeof rawDefinition === 'object' && !Array.isArray(rawDefinition)
      ? rawDefinition as Record<string, unknown>
      : {}
    const rawMedia = definition.media && typeof definition.media === 'object' && !Array.isArray(definition.media)
      ? definition.media as Record<string, unknown>
      : {}
    return {
      definition: {
        ...definition,
        media: {
          ...rawMedia,
          src: asset.url,
          mimeType: asset.mimeType,
          durationMs: asset.durationMs,
          transcript: asset.transcript,
          tracks: asset.captions,
        },
      },
      state,
      onStateChange: (next: DidactValue) => {
        setState(next)
        void ports.persistence?.save(
          { organizationId: '', courseId: '' },
          `interactive-media:${activityId}`,
          next,
        )
      },
      renderActivity: (
        child: { authoring?: Record<string, unknown> },
        context: { complete: () => void },
      ) => <EmbeddedCheckpoint authoring={child.authoring ?? {}} complete={context.complete} />,
    }
  }, [activityId, asset, componentId, componentProps, ports.evaluation, ports.persistence, state])

  if (failed) return <Status kind="failed">No se pudo resolver el recurso de esta actividad.</Status>
  if (!asset) return <Status kind="loading">Cargando recurso accesible…</Status>
  if (componentId === 'didact.interactive-media') {
    const definition = mountedProps.definition as Record<string, unknown>
    const media = definition.media as Record<string, unknown>
    if (media.kind === 'audio' && !asset.transcript?.length) {
      return <Status kind="blocked">El audio no tiene una transcripción accesible.</Status>
    }
    if (media.kind === 'video' && media.noSpeech !== true && !asset.captions?.length) {
      return <Status kind="blocked">El vídeo con voz no tiene subtítulos.</Status>
    }
  }
  return <DidactComponentMount componentId={componentId} componentProps={mountedProps} ports={ports} />
}
