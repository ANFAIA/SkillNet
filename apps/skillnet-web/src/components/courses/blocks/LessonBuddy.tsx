import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ChatMarkdown } from '../../chat/ChatMarkdown'
import { duration, ease } from '../../../lib/motion'

// ── Types ──────────────────────────────────────────────────────

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  isStreaming?: boolean
}

export interface LessonBuddyProps {
  /** Current node title — gives the AI context. */
  nodeTitle?: string
  /** Current node summary. */
  nodeSummary?: string
  /** Step index in the stepper (0-based). */
  stepIndex: number
  /** Total steps. */
  totalSteps: number
}

// ── SSE streaming (same pattern as ExplainModal) ───────────────

async function streamChat(
  message: string,
  signal: AbortSignal,
  onToken: (chunk: string) => void,
): Promise<void> {
  const res = await fetch('/api/v1/chat/admin', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
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
        } catch { /* skip */ }
        eventType = ''
      }
    }
  }
}

// ── Component ──────────────────────────────────────────────────

export function LessonBuddy({
  nodeTitle,
  nodeSummary,
  stepIndex,
  totalSteps,
}: LessonBuddyProps) {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages])

  // Focus input when opening
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 100)
  }, [open])

  // Clean up on unmount
  useEffect(() => () => abortRef.current?.abort(), [])

  const send = useCallback(
    async (text: string) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      const userMsg: Message = { id: crypto.randomUUID(), role: 'user', content: text }
      const assistantId = crypto.randomUUID()
      const assistantMsg: Message = { id: assistantId, role: 'assistant', content: '', isStreaming: true }

      setMessages((prev) => [...prev, userMsg, assistantMsg])
      setIsStreaming(true)

      // Seed context on first message
      const seeded = messages.length === 0
        ? `Contexto: el alumno esta en el paso ${stepIndex + 1} de ${totalSteps} del nodo "${nodeTitle || 'sin titulo'}". Resumen del nodo: "${nodeSummary || ''}". Su pregunta: ${text}`
        : text

      try {
        await streamChat(seeded, controller.signal, (chunk) => {
          if (controller.signal.aborted) return
          setMessages((prev) =>
            prev.map((m) => m.id === assistantId ? { ...m, content: m.content + chunk } : m),
          )
        })
      } catch (err) {
        if ((err as Error).name === 'AbortError') return
        setMessages((prev) =>
          prev.map((m) => m.id === assistantId ? { ...m, content: m.content || 'Error al conectar.', isStreaming: false } : m),
        )
      } finally {
        if (abortRef.current === controller) {
          setIsStreaming(false)
          setMessages((prev) => prev.map((m) => m.id === assistantId ? { ...m, isStreaming: false } : m))
        }
      }
    },
    [messages.length, stepIndex, totalSteps, nodeTitle, nodeSummary],
  )

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const text = inputRef.current?.value.trim()
    if (!text) return
    if (inputRef.current) inputRef.current.value = ''
    send(text)
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  return (
    <>
      {/* Floating avatar button */}
      <AnimatePresence>
        {!open && (
          <motion.button
            type="button"
            onClick={() => setOpen(true)}
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.8, opacity: 0 }}
            transition={{ duration: duration.normal, ease: [...ease.bounce] }}
            className="fixed bottom-6 right-6 z-50 w-12 h-12 rounded-full bg-primary shadow-lg flex items-center justify-center hover:scale-105 transition-transform"
            aria-label="Abrir asistente"
          >
            <img src="/logo.png" alt="" className="w-7 h-7" />
          </motion.button>
        )}
      </AnimatePresence>

      {/* Chat bubble */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            transition={{ duration: duration.normal, ease: [...ease.base] }}
            className="fixed bottom-6 right-6 z-50 w-80 max-h-[60vh] bg-bg border border-border rounded-2xl shadow-xl flex flex-col overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center gap-2.5 px-4 py-3 border-b border-border">
              <div className="w-7 h-7 rounded-full bg-primary flex items-center justify-center flex-shrink-0">
                <img src="/logo.png" alt="" className="w-4 h-4" />
              </div>
              <span className="text-sm font-medium text-text flex-1">Asistente</span>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-text-muted hover:text-text transition-colors text-lg leading-none"
                aria-label="Cerrar"
              >
                &times;
              </button>
            </div>

            {/* Messages */}
            <div
              ref={scrollRef}
              className="flex-1 overflow-y-auto px-4 py-3 space-y-3"
              style={{ scrollbarWidth: 'thin' }}
            >
              {messages.length === 0 && (
                <p className="text-xs text-text-muted">
                  Preguntame lo que quieras sobre esta leccion.
                </p>
              )}
              {messages.map((msg) => (
                <div key={msg.id} className={msg.role === 'user' ? 'text-right' : ''}>
                  {msg.role === 'user' ? (
                    <span className="inline-block bg-primary/10 px-3 py-1.5 rounded-2xl text-sm text-text max-w-[90%]">
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
            <form onSubmit={handleSubmit} className="flex items-end gap-2 px-3 pb-3 pt-1 border-t border-border">
              <textarea
                ref={inputRef}
                onKeyDown={onKeyDown}
                rows={1}
                placeholder="Escribe tu pregunta..."
                disabled={isStreaming}
                className="flex-1 min-h-[36px] max-h-[80px] resize-none rounded-xl bg-bg-subtle px-3 py-2 text-sm text-text outline-none placeholder:text-text-muted disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={isStreaming}
                aria-label="Enviar"
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-white disabled:opacity-30 transition-colors"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 12h13" /><path d="M12 5l7 7-7 7" />
                </svg>
              </button>
            </form>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
