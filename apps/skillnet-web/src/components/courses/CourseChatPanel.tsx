import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { useIntl } from 'react-intl'
import { NodeChat } from './NodeChat'
import { ExplainLayer } from './explainLayer'
import { EXPLAIN_LAYER_COURSE_CHAT } from './explainLayers'
import { backdrop, transition } from '../../lib/motion'

interface CourseChatPanelProps {
  open: boolean
  onClose: () => void
  courseId: string
  courseTitle: string
}

export function CourseChatPanel({ open, onClose, courseId, courseTitle }: CourseChatPanelProps) {
  const intl = useIntl()
  const [hasOpened, setHasOpened] = useState(open)

  useEffect(() => {
    if (open) setHasOpened(true)
  }, [open])

  useEffect(() => {
    if (!open) return
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [onClose, open])

  if (!hasOpened) return null

  return createPortal(
    <div className={`fixed inset-0 z-[100] ${open ? '' : 'pointer-events-none'}`} aria-hidden={!open}>
      <AnimatePresence>
        {open && (
          <motion.button
            type="button"
            aria-label={intl.formatMessage({ id: 'panel.close' })}
            className="absolute inset-0 h-full w-full bg-slate-950/25 backdrop-blur-sm"
            {...backdrop}
            onClick={onClose}
          />
        )}
      </AnimatePresence>

      <motion.aside
        role={open ? 'dialog' : undefined}
        aria-modal={open ? 'true' : undefined}
        aria-labelledby={open ? 'course-chat-title' : undefined}
        initial={false}
        animate={{ x: open ? 0 : '100%' }}
        transition={open ? transition.pushIn : transition.pushOut}
        className="absolute inset-y-0 right-0 flex w-full flex-col border-l border-border bg-surface shadow-2xl sm:max-w-md"
      >
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <h2 id="course-chat-title" className="text-base font-semibold text-text">
              {intl.formatMessage({ id: 'courseChat.title' })}
            </h2>
            <p className="mt-0.5 truncate text-sm text-text-secondary">{courseTitle}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={intl.formatMessage({ id: 'panel.close' })}
            className="flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-full text-text-muted transition-colors hover:bg-bg-muted hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </header>

        <div className="min-h-0 flex-1 p-5">
          <ExplainLayer zIndex={EXPLAIN_LAYER_COURSE_CHAT}>
            <NodeChat courseId={courseId} />
          </ExplainLayer>
        </div>
      </motion.aside>
    </div>,
    document.body,
  )
}
