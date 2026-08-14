import { useMemo, useState } from 'react'
import { useIntl } from 'react-intl'
import { useCourseArtifacts, type MediaArtifactRead } from '../../api/media'
import type { CompanionModality } from '../../api/onboarding'
import { Modal } from '../ui'
import { CourseArtifactView } from './CourseArtifactView'

type NodeModalityAccessProps = {
  courseId: string
  nodeId: string
  preferred: CompanionModality[]
}

const KINDS: Record<CompanionModality, string> = {
  audio: 'podcast',
  video: 'video',
}

export function NodeModalityAccess({ courseId, nodeId, preferred }: NodeModalityAccessProps) {
  const intl = useIntl()
  const { data } = useCourseArtifacts(courseId)
  const [openArtifact, setOpenArtifact] = useState<MediaArtifactRead | null>(null)

  const artifacts = useMemo(() => {
    const eligible = (data ?? []).filter(
      (artifact) =>
        artifact.status === 'done' &&
        (artifact.node_id === null || artifact.node_id === nodeId),
    )
    return Object.fromEntries(
      (Object.keys(KINDS) as CompanionModality[]).map((modality) => [
        modality,
        eligible.find((artifact) => artifact.kind === KINDS[modality]) ?? null,
      ]),
    ) as Record<CompanionModality, MediaArtifactRead | null>
  }, [data, nodeId])

  const available = (Object.keys(KINDS) as CompanionModality[]).filter(
    (modality) => artifacts[modality] !== null,
  )
  const visible = [...new Set([...preferred, ...available])]
  if (visible.length === 0) return null

  return (
    <>
      <nav
        aria-label={intl.formatMessage({ id: 'node.modalities' })}
        className="mb-4 flex flex-wrap items-center gap-2"
        data-no-explain=""
      >
        <span className="mr-1 text-xs font-medium text-text-muted">
          {intl.formatMessage({ id: 'node.modalities' })}
        </span>
        {visible.map((modality) => {
          const artifact = artifacts[modality]
          const isPreferred = preferred.includes(modality)
          return (
            <button
              key={modality}
              type="button"
              disabled={!artifact}
              onClick={() => artifact && setOpenArtifact(artifact)}
              className={`rounded-md border px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                isPreferred
                  ? 'border-primary bg-primary-subtle text-primary'
                  : 'border-border text-text-secondary hover:bg-bg-muted'
              }`}
            >
              {intl.formatMessage({ id: `node.modality.${modality}` })}
              {!artifact && ` · ${intl.formatMessage({ id: 'node.modality.pending' })}`}
            </button>
          )
        })}
      </nav>

      <Modal open={openArtifact !== null} onClose={() => setOpenArtifact(null)} size="lg">
        {openArtifact && <CourseArtifactView artifact={openArtifact} />}
      </Modal>
    </>
  )
}
