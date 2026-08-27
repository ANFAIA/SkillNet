import { useIntl } from 'react-intl'
import type { NodeKnowledgePack } from '../../types'

const STATUS_KEY = {
  pending: 'schema.packPending',
  ready: 'schema.packReady',
  review_required: 'schema.packReviewRequired',
  stale: 'schema.packStale',
  failed: 'schema.packFailed',
} as const

function statusClass(status: NodeKnowledgePack['status']) {
  if (status === 'ready') return 'text-success'
  if (status === 'review_required' || status === 'failed') return 'text-danger'
  return 'text-text-muted'
}

export function NodeKnowledgePreparation({
  pack,
  loading,
}: {
  pack: NodeKnowledgePack | undefined
  loading: boolean
}) {
  const intl = useIntl()
  const preparing = loading || !pack || pack.status === 'pending' || pack.status === 'stale'

  return (
    <div className="px-2 py-2 border-t border-border mt-2">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="font-medium text-text">
          {intl.formatMessage({ id: 'schema.packTitle' })}
        </span>
        <span
          role="status"
          className={preparing ? 'text-text-muted' : statusClass(pack.status)}
        >
          {preparing
            ? intl.formatMessage({ id: 'schema.packPending' })
            : intl.formatMessage({ id: STATUS_KEY[pack.status] })}
        </span>
      </div>

      {preparing && (
        <p className="text-xs text-text-muted mt-1">
          {intl.formatMessage({ id: 'schema.packPreparingDesc' })}
        </p>
      )}

      {pack?.status === 'ready' && (
        <p className="text-xs text-text-muted mt-1">
          {intl.formatMessage({ id: 'schema.packReadyDesc' })}
        </p>
      )}

      {pack?.status === 'review_required' && (
        <div className="mt-1 text-xs text-text-secondary">
          <p>{intl.formatMessage({ id: 'schema.packReviewDesc' })}</p>
          {pack.blocking_gaps.length > 0 && (
            <ul className="list-disc pl-4 mt-1 text-danger">
              {pack.blocking_gaps.map((gap) => <li key={gap}>{gap}</li>)}
            </ul>
          )}
        </div>
      )}

      {pack?.status === 'failed' && (
        <p role="alert" className="text-xs text-danger mt-1">
          {intl.formatMessage({ id: 'schema.packFailedDesc' })}
        </p>
      )}
    </div>
  )
}
