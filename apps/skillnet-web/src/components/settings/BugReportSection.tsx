import { useState } from 'react'
import { useIntl } from 'react-intl'
import { Badge, Button, Input, Textarea } from '../ui'
import { useMyBugReports, useReportBug } from '../../api/bug-reports'
import { apiErrorMessage } from '../../lib/apiErrors'
import { describeEnvironment } from '../../lib/environment'
import { usePreferences } from '../../stores/preferences'
import type { BugReportStatus } from '../../types'

const STATUS_VARIANT: Record<BugReportStatus, 'primary' | 'accent' | 'warning' | 'danger'> = {
  pending: 'warning',
  issue: 'accent',
  discarded: 'primary',
  failed: 'danger',
}

/**
 * Report a problem with the app, and follow what happened to it. The page and the browser
 * are added on their own; the person only writes what went wrong.
 */
export function BugReportSection() {
  const intl = useIntl()
  const locale = usePreferences((s) => s.locale)
  const report = useReportBug()
  const mine = useMyBugReports()
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')

  const canSend = title.trim() !== '' && body.trim() !== '' && !report.isPending

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!canSend) return
    report.mutate(
      {
        title: title.trim(),
        body: body.trim(),
        page_path: window.location.pathname,
        environment: describeEnvironment(locale),
      },
      {
        onSuccess: () => {
          setTitle('')
          setBody('')
        },
      },
    )
  }

  return (
    <div>
      <form onSubmit={submit} className="space-y-3 max-w-xl">
        <Input
          label={intl.formatMessage({ id: 'bugReport.titleLabel' })}
          value={title}
          maxLength={200}
          onChange={(e) => setTitle(e.target.value)}
        />
        <Textarea
          label={intl.formatMessage({ id: 'bugReport.bodyLabel' })}
          value={body}
          rows={4}
          maxLength={5000}
          onChange={(e) => setBody(e.target.value)}
        />
        <p className="text-xs text-text-muted">
          {intl.formatMessage({ id: 'bugReport.privacy' })}
        </p>
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={!canSend}>
            {intl.formatMessage({ id: report.isPending ? 'bugReport.sending' : 'bugReport.submit' })}
          </Button>
          {report.isSuccess && (
            <p role="status" className="text-sm text-text-secondary">
              {intl.formatMessage({ id: 'bugReport.sent' })}
            </p>
          )}
          {report.isError && (
            <p role="alert" className="text-sm text-danger">
              {apiErrorMessage(intl, report.error, 'bugReport.error')}
            </p>
          )}
        </div>
      </form>

      {mine.data && mine.data.length > 0 && (
        <h3 className="text-sm font-semibold text-text mt-6 mb-2">
          {intl.formatMessage({ id: 'bugReport.mine' })}
        </h3>
      )}
      {mine.data && mine.data.length > 0 && (
        <ul className="max-h-60 overflow-y-auto divide-y divide-border border-y border-border">
          {mine.data?.map((r) => (
            <li key={r.id} className="py-3 flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="text-sm font-medium text-text truncate">{r.title}</p>
                {r.reason && <p className="text-sm text-text-secondary mt-0.5">{r.reason}</p>}
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
              </div>
              <Badge variant={STATUS_VARIANT[r.status]} badgeStyle="plain" className="shrink-0">
                {intl.formatMessage({ id: `bugReport.status.${r.status}` })}
              </Badge>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
