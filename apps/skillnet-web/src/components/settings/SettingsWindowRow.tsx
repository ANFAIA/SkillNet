import { useRef, useState } from 'react'
import { Button, Modal } from '../ui'
import { SettingRow } from './SettingRow'

/**
 * A settings row whose button opens a window that grows from the button. Keeps a form or a list
 * out of the page until someone asks for it, so Settings stays a column of quiet rows.
 */
export function SettingsWindowRow({
  title,
  description,
  action,
  windowTitle,
  size = 'md',
  tone = 'secondary',
  children,
}: {
  title: string
  description?: string
  action: string
  windowTitle: string
  size?: 'md' | 'lg'
  tone?: 'secondary' | 'danger'
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
          variant={tone === 'danger' ? 'danger' : 'secondary'}
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
