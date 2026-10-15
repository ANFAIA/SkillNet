import { useIntl } from 'react-intl'
import { Badge, Button } from '../ui'
import { useAdminBugReports, useDiscardBugReport, useFileBugReport } from '../../api/bug-reports'
import { apiErrorMessage } from '../../lib/apiErrors'
import type { BugReportStatus } from '../../types'

const STATUS_VARIANT: Record<BugReportStatus, 'primary' | 'accent' | 'warning' | 'danger'> = {
  pending: 'warning',
  issue: 'accent',
  discarded: 'primary',
  failed: 'danger',
}

/** Every report from the organization, with the two things an admin can do to one that is not
 *  filed: send it to GitHub now, or discard it. */
export function BugReportsAdmin() {
  const intl = useIntl()
  const reports = useAdminBugReports()
  const file = useFileBugReport()
  const discard = useDiscardBugReport()
  const busy = file.isPending || discard.isPending
  const actionError = file.error ?? discard.error

  if (reports.data && reports.data.length === 0) {
    return (
      <p className="text-sm text-text-secondary">{intl.formatMessage({ id: 'bugReport.admin.empty' })}</p>
    )
  }

  return (
    <div>
      <ul className="divide-y divide-border border-y border-border">
        {reports.data?.map((r) => (
          <li key={r.id} className="py-3">
            <div className="flex items-start justify-between gap-4">
              <p className="text-sm font-medium text-text min-w-0">{r.title}</p>
              <Badge variant={STATUS_VARIANT[r.status]} badgeStyle="plain" className="shrink-0">
                {intl.formatMessage({ id: `bugReport.status.${r.status}` })}
              </Badge>
            </div>
            <p className="text-sm text-text-secondary mt-1 whitespace-pre-line">{r.body}</p>
            {r.reason && <p className="text-xs text-text-muted mt-1">{r.reason}</p>}
            <div className="flex items-center gap-3 mt-2">
              {r.issue_url && (
                <a
                  href={r.issue_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm text-primary hover:underline"
                >
                  {intl.formatMessage({ id: 'bugReport.viewIssue' })}
                </a>
              )}
              {r.status !== 'issue' && (
                <>
                  <Button size="sm" disabled={busy} onClick={() => file.mutate(r.id)}>
                    {intl.formatMessage({ id: 'bugReport.admin.file' })}
                  </Button>
                  {r.status !== 'discarded' && (
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={busy}
                      onClick={() => discard.mutate(r.id)}
                    >
                      {intl.formatMessage({ id: 'bugReport.admin.discard' })}
                    </Button>
                  )}
                </>
              )}
            </div>
          </li>
        ))}
      </ul>
      {actionError && (
        <p role="alert" className="text-sm text-danger mt-3">
          {apiErrorMessage(intl, actionError, 'bugReport.admin.actionError')}
        </p>
      )}
    </div>
  )
}
