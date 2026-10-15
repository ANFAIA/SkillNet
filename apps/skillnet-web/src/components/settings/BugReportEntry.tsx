import { useIntl } from 'react-intl'
import { BugReportSection } from './BugReportSection'
import { BugReportsAdmin } from './BugReportsAdmin'
import { SettingsWindowRow } from './SettingsWindowRow'

/** Report a problem. Rare and technical, so it is one quiet row in Settings. */
export function BugReportEntry() {
  const intl = useIntl()
  return (
    <SettingsWindowRow
      title={intl.formatMessage({ id: 'bugReport.title' })}
      action={intl.formatMessage({ id: 'bugReport.action' })}
      windowTitle={intl.formatMessage({ id: 'bugReport.title' })}
      size="md"
    >
      <BugReportSection />
    </SettingsWindowRow>
  )
}

/** For admins: every report from the organization. */
export function BugReportsAdminEntry() {
  const intl = useIntl()
  return (
    <SettingsWindowRow
      title={intl.formatMessage({ id: 'bugReport.admin.title' })}
      action={intl.formatMessage({ id: 'bugReport.admin.open' })}
      windowTitle={intl.formatMessage({ id: 'bugReport.admin.title' })}
      size="lg"
    >
      <BugReportsAdmin />
    </SettingsWindowRow>
  )
}
