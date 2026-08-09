/**
 * Lesson buddy — SkillNet's spider mascot hanging from a thread in the
 * top-right corner with a speech bubble. Click to open an AI chat.
 * Inspired by Brilliant's Koji: proactive, inline, contextual.
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useIntl } from 'react-intl'
import { ChatInput } from '../../chat/ChatInput'
import { ChatMarkdown } from '../../chat/ChatMarkdown'
import { duration, ease } from '../../../lib/motion'
import { executeTool } from '../../../lib/toolRegistry'

// ── Types ──────────────────────────────────────────────────────

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  isStreaming?: boolean
}

export interface LessonBuddyProps {
  nodeTitle?: string
  nodeSummary?: string
  stepIndex: number
  totalSteps: number
}

// ── SSE streaming ──────────────────────────────────────────────

async function streamChat(
  message: string,
  context: Record<string, unknown> | undefined,
  signal: AbortSignal,
  onToken: (chunk: string) => void,
): Promise<void> {
  const res = await fetch('/api/v1/chat', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, context }),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`${res.status}`)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let eventType = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      if (line.startsWith('event:')) {
        eventType = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        const raw = line.slice(5).trim()
        if (!raw) continue
        try {
          const data = JSON.parse(raw) as Record<string, unknown>
          if (eventType === 'token') onToken(String(data.content ?? ''))
          else if (eventType === 'action') {
            const tool = String(data.tool ?? '')
            const args = (data.args ?? {}) as Record<string, unknown>
            if (tool) executeTool(tool, args)
          }
        } catch { /* skip */ }
        eventType = ''
      }
    }
  }
}

// ── Proactive hints ────────────────────────────────────────────

function proactiveHintId(stepIndex: number, totalSteps: number): string {
  if (stepIndex === 0) return 'buddy.hint.start'
  if (stepIndex === totalSteps - 1) return 'buddy.hint.last'
  if (stepIndex === 1) return 'buddy.hint.middle'
  return 'buddy.hint.default'
}

// ── Component ──────────────────────────────────────────────────

export function LessonBuddy({
  nodeTitle,
  nodeSummary,
  stepIndex,
  totalSteps,
}: LessonBuddyProps) {
  const intl = useIntl()
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [buddyInput, setBuddyInput] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages])

  useEffect(() => () => abortRef.current?.abort(), [])

  const send = useCallback(
    async (text: string) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      const userMsg: Message = { id: crypto.randomUUID(), role: 'user', content: text }
      const aId = crypto.randomUUID()
      const aMsg: Message = { id: aId, role: 'assistant', content: '', isStreaming: true }

      setMessages((prev) => [...prev, userMsg, aMsg])
      setIsStreaming(true)

      // On the first message, send node context via the `context` field so
      // the backend can use it for grounding without polluting the session
      // title (which is derived from the message text).
      const ctx = messages.length === 0
        ? { step: stepIndex + 1, totalSteps, nodeTitle: nodeTitle ?? '', nodeSummary: nodeSummary ?? '' }
        : undefined

      try {
        await streamChat(text, ctx, controller.signal, (chunk) => {
          if (controller.signal.aborted) return
          setMessages((prev) =>
            prev.map((m) => m.id === aId ? { ...m, content: m.content + chunk } : m),
          )
        })
      } catch (err) {
        if ((err as Error).name === 'AbortError') return
        setMessages((prev) =>
          prev.map((m) => m.id === aId ? { ...m, content: m.content || 'Error.', isStreaming: false } : m),
        )
      } finally {
        if (abortRef.current === controller) {
          setIsStreaming(false)
          setMessages((prev) => prev.map((m) => m.id === aId ? { ...m, isStreaming: false } : m))
        }
      }
    },
    [messages.length, stepIndex, totalSteps, nodeTitle, nodeSummary],
  )

  function handleBuddySend() {
    const text = buddyInput.trim()
    if (!text) return
    setBuddyInput('')
    send(text)
  }

  const hint = intl.formatMessage({ id: proactiveHintId(stepIndex, totalSteps) })

  return (
    <div className="flex items-end justify-end gap-3">
      {/* Speech bubble + chat */}
      <AnimatePresence mode="wait">
        {!open ? (
          /* Collapsed: speech bubble with proactive hint */
          <motion.button
            key="bubble"
            type="button"
            onClick={() => setOpen(true)}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: duration.normal, ease: [...ease.base] }}
            className="relative bg-bg border border-border rounded-2xl rounded-br-sm px-3 py-2 text-xs text-text-muted hover:text-text hover:border-primary/30 transition-colors max-w-[200px] text-left"
            aria-label={intl.formatMessage({ id: 'buddy.assistant' })}
          >
            <AnimatePresence mode="wait">
              <motion.span
                key={`hint-${stepIndex}`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: duration.fast }}
              >
                {hint}
              </motion.span>
            </AnimatePresence>
          </motion.button>
        ) : (
          /* Expanded: chat card — max-width prevents overflow on small screens */
          <motion.div
            key="chat"
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            transition={{ duration: duration.normal, ease: [...ease.base] }}
            className="w-72 max-w-[calc(100vw-5rem)] border border-border rounded-2xl rounded-br-sm bg-bg overflow-hidden flex flex-col"
            style={{ maxHeight: 'min(50vh, 360px)' }}
          >
            {/* Header */}
            <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
              <span className="text-sm font-medium text-text flex-1">{intl.formatMessage({ id: 'buddy.assistant' })}</span>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-text-muted hover:text-text transition-colors text-base leading-none p-1"
                aria-label={intl.formatMessage({ id: 'buddy.close' })}
              >
                &times;
              </button>
            </div>

            {/* Messages */}
            <div
              ref={scrollRef}
              className="flex-1 overflow-y-auto px-3 py-2.5 space-y-2"
              style={{ scrollbarWidth: 'thin' }}
            >
              {messages.length === 0 && (
                <p className="text-xs text-text-muted">
                  {intl.formatMessage({ id: 'buddy.askAnything' })}
                </p>
              )}
              {messages.map((msg) => (
                <div key={msg.id} className={msg.role === 'user' ? 'text-right' : ''}>
                  {msg.role === 'user' ? (
                    <span className="inline-block bg-primary/10 px-3 py-1.5 rounded-2xl text-sm text-text max-w-[85%]">
                      {msg.content}
                    </span>
                  ) : (
                    <div className="text-sm text-text">
                      <ChatMarkdown content={msg.content} isStreaming={msg.isStreaming} />
                      {msg.isStreaming && !msg.content && (
                        <span className="typing-dots"><span /><span /><span /></span>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Input */}
            <form onSubmit={(e) => { e.preventDefault(); handleBuddySend() }} className="px-3 pb-2 pt-1 border-t border-border">
              <ChatInput
                value={buddyInput}
                onChange={setBuddyInput}
                onSend={handleBuddySend}
                isStreaming={isStreaming}
                disabled={isStreaming}
                placeholder={intl.formatMessage({ id: 'buddy.placeholder' })}
                size="sm"
                autoFocus
              />
            </form>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Spider hanging from thread */}
      <div className="flex flex-col items-center shrink-0">
        {/* Thread */}
        <div className="w-px h-8 bg-border" />
        {/* Spider */}
        <motion.div
          className="w-10 h-10 cursor-pointer"
          onClick={() => setOpen((o) => !o)}
          animate={{ y: [0, 3, 0] }}
          transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
          aria-label="SkillNet mascot"
        >
          <img src="/spider.svg" alt="" className="w-full h-full" />
        </motion.div>
      </div>
    </div>
  )
}
