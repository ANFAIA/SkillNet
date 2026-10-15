import { useRef, useState } from 'react'
import { useIntl } from 'react-intl'
import { Button, Modal } from '../ui'
import { BugReportSection } from './BugReportSection'
import { BugReportsAdmin } from './BugReportsAdmin'
import { SettingRow } from './SettingRow'

/** A settings row whose button opens a window that grows from the button. */
function WindowRow({
  title,
  description,
  action,
  windowTitle,
  size,
  children,
}: {
  title: string
  description: string
  action: string
  windowTitle: string
  size: 'md' | 'lg'
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(false)
  const [origin, setOrigin] = useState<DOMRect | null>(null)
  const button = useRef<HTMLButtonElement>(null)

  return (
    <>
      <SettingRow title={title} description={description}>
        <Button
          ref={button}
          variant="secondary"
          size="sm"
          className="shrink-0"
          onClick={() => {
            setOrigin(button.current?.getBoundingClientRect() ?? null)
            setOpen(true)
          }}
        >
          {action}
        </Button>
      </SettingRow>
      <Modal open={open} onClose={() => setOpen(false)} origin={origin} size={size}>
        <h2 className="text-lg font-semibold text-text mb-4">{windowTitle}</h2>
        {children}
      </Modal>
    </>
  )
}

/** Report a problem. Rare and technical, so it is one quiet row in Settings. */
export function BugReportEntry() {
  const intl = useIntl()
  return (
    <WindowRow
      title={intl.formatMessage({ id: 'bugReport.title' })}
      description={intl.formatMessage({ id: 'bugReport.hint' })}
      action={intl.formatMessage({ id: 'bugReport.title' })}
      windowTitle={intl.formatMessage({ id: 'bugReport.title' })}
      size="md"
    >
      <BugReportSection />
    </WindowRow>
  )
}

/** For admins: every report from the organization. */
export function BugReportsAdminEntry() {
  const intl = useIntl()
  return (
    <WindowRow
      title={intl.formatMessage({ id: 'bugReport.admin.title' })}
      description={intl.formatMessage({ id: 'bugReport.admin.hint' })}
      action={intl.formatMessage({ id: 'bugReport.admin.open' })}
      windowTitle={intl.formatMessage({ id: 'bugReport.admin.title' })}
      size="lg"
    >
      <BugReportsAdmin />
    </WindowRow>
  )
}
