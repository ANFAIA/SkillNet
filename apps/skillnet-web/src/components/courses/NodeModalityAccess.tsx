import { useEffect, useState, type ReactNode } from 'react'
import { useIntl } from 'react-intl'
import { useMediaArtifact, useRequestNodeModality } from '../../api/media'
import type { CompanionModality } from '../../api/onboarding'
import { Button } from '../ui'
import { NodeModalityView } from './NodeModalityView'

type Selection = 'web' | CompanionModality

type NodeModalityAccessProps = {
  nodeId: string
  preferred: CompanionModality[]
  children: ReactNode
}

export function NodeModalityAccess({ nodeId, preferred, children }: NodeModalityAccessProps) {
  const intl = useIntl()
  const [selected, setSelected] = useState<Selection>('web')
  const [artifactIds, setArtifactIds] = useState<Partial<Record<CompanionModality, string>>>({})
  const audioRequest = useRequestNodeModality(nodeId)
  const videoRequest = useRequestNodeModality(nodeId)
  const activeRequest = selected === 'audio' ? audioRequest : videoRequest
  const activeId = selected === 'web' ? undefined : artifactIds[selected]
  const artifact = useMediaArtifact(activeId)

  useEffect(() => {
    setSelected('web')
    setArtifactIds({})
    audioRequest.reset()
    videoRequest.reset()
  }, [nodeId]) // eslint-disable-line react-hooks/exhaustive-deps -- reset the node-local player

  function activate(modality: CompanionModality) {
    setSelected(modality)
    if (artifactIds[modality]) return
    const modalityRequest = modality === 'audio' ? audioRequest : videoRequest
    modalityRequest.mutate(
      { modality, language: intl.locale.toLowerCase().startsWith('en') ? 'en' : 'es' },
      {
        onSuccess: (result) => {
          setArtifactIds((current) => ({ ...current, [modality]: result.artifact_id }))
        },
      },
    )
  }

  function retry() {
    if (selected === 'web') return
    activeRequest.mutate(
      { modality: selected, language: intl.locale.toLowerCase().startsWith('en') ? 'en' : 'es' },
      {
        onSuccess: (result) => {
          setArtifactIds((current) => ({ ...current, [selected]: result.artifact_id }))
        },
      },
    )
  }

  if (preferred.length === 0) return <>{children}</>

  const loading =
    selected !== 'web' &&
    (activeRequest.isPending || !activeId || artifact.isLoading || artifact.data?.status === 'pending' || artifact.data?.status === 'running')
  const failed =
    selected !== 'web' &&
    (activeRequest.isError || artifact.isError || artifact.data?.status === 'error')
  const ready = selected !== 'web' && artifact.data?.status === 'done'

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <nav
        aria-label={intl.formatMessage({ id: 'node.modalities' })}
        className="mb-4 flex shrink-0 items-center gap-1 border-b border-border"
        data-no-explain=""
      >
        {(['web', ...preferred] as Selection[]).map((modality) => (
          <button
            key={modality}
            type="button"
            aria-pressed={selected === modality}
            onClick={() => modality === 'web' ? setSelected('web') : activate(modality)}
            className={`border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
              selected === modality
                ? 'border-primary text-primary'
                : 'border-transparent text-text-muted hover:text-text'
            }`}
          >
            {intl.formatMessage({ id: `node.modality.${modality}` })}
          </button>
        ))}
      </nav>

      <div className="min-h-0 flex-1" hidden={selected !== 'web'}>{children}</div>

      {selected !== 'web' && (
        <section className="flex min-h-64 flex-1 flex-col justify-center" aria-live="polite">
          {loading && !failed && (
            <div className="mx-auto max-w-md text-center" role="status">
              <div className="mx-auto mb-4 size-5 animate-spin rounded-full border-2 border-border border-t-primary" />
              <p className="text-sm font-medium text-text">
                {intl.formatMessage({ id: 'node.modality.preparing' }, {
                  modality: intl.formatMessage({ id: `node.modality.${selected}` }),
                })}
              </p>
              <p className="mt-1 text-xs text-text-muted">
                {intl.formatMessage({ id: 'node.modality.onDemand' })}
              </p>
            </div>
          )}
          {failed && (
            <div className="mx-auto max-w-md text-center" role="alert">
              <p className="text-sm text-danger">
                {intl.formatMessage({ id: 'node.modality.failed' }, {
                  modality: intl.formatMessage({ id: `node.modality.${selected}` }),
                })}
              </p>
              <Button className="mt-3" variant="secondary" onClick={retry} disabled={activeRequest.isPending}>
                {intl.formatMessage({ id: 'node.modality.retry' })}
              </Button>
            </div>
          )}
          {ready && artifact.data && <NodeModalityView artifact={artifact.data} />}
        </section>
      )}
    </div>
  )
}
