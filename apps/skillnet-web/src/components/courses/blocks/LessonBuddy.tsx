/**
 * Inline AI lesson buddy — Curio-style: a small avatar that morphs into a
 * chat bubble when tapped. Uses the same visual language as ExplainPopover
 * (floating card, rounded, border) and layout animation for the morph.
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { AnimatePresence, LayoutGroup, motion } from 'framer-motion'
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
  nodeTitle?: string
  nodeSummary?: string
  stepIndex: number
  totalSteps: number
}

/** Proactive hints by step position — the buddy speaks first, like Koji. */
function proactiveHint(stepIndex: number, totalSteps: number): string {
  if (stepIndex === 0) return 'Veamos de que va esto...'
  if (stepIndex === totalSteps - 1) return 'A ver que tal se te da!'
  if (stepIndex === 1) return 'Fijate bien, esto es lo importante.'
  return 'Sigue asi, ya queda poco.'
}

// ── SSE streaming ──────────────────────────────────────────────

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

// ── Morph transition ───────────────────────────────────────────

const morphSpring = { type: 'spring' as const, stiffness: 300, damping: 30 }

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

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [messages])

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 200)
  }, [open])

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

      const seeded = messages.length === 0
        ? `Contexto: el alumno esta en el paso ${stepIndex + 1} de ${totalSteps} del nodo "${nodeTitle || ''}". Resumen: "${nodeSummary || ''}". Pregunta: ${text}`
        : text

      try {
        await streamChat(seeded, controller.signal, (chunk) => {
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
    <LayoutGroup id="lesson-buddy">
      <AnimatePresence mode="wait">
        {!open ? (
          /* ── Collapsed: pill with avatar + proactive hint ── */
          <motion.button
            key="collapsed"
            layoutId="buddy-container"
            type="button"
            onClick={() => setOpen(true)}
            className="flex items-center gap-2 px-3 py-2 rounded-full border border-border bg-bg hover:bg-bg-subtle transition-colors"
            transition={morphSpring}
            aria-label="Abrir asistente"
          >
            <motion.img
              layoutId="buddy-avatar"
              src="/logo.png"
              alt=""
              className="w-5 h-5"
              transition={morphSpring}
            />
            <AnimatePresence mode="wait">
              <motion.span
                key={`hint-${stepIndex}`}
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 4 }}
                transition={{ duration: duration.normal, ease: [...ease.base] }}
                className="text-xs text-text-muted"
              >
                {proactiveHint(stepIndex, totalSteps)}
              </motion.span>
            </AnimatePresence>
          </motion.button>
        ) : (
          /* ── Expanded: chat card ── */
          <motion.div
            key="expanded"
            layoutId="buddy-container"
            className="w-full max-w-sm border border-border rounded-2xl bg-bg overflow-hidden flex flex-col"
            style={{ maxHeight: 'min(50vh, 400px)' }}
            transition={morphSpring}
          >
            {/* Header */}
            <div className="flex items-center gap-2 px-3 py-2.5 border-b border-border">
              <motion.img
                layoutId="buddy-avatar"
                src="/logo.png"
                alt=""
                className="w-5 h-5"
                transition={morphSpring}
              />
              <span className="text-sm font-medium text-text flex-1">Asistente</span>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-text-muted hover:text-text transition-colors text-base leading-none p-1"
                aria-label="Cerrar"
              >
                &times;
              </button>
            </div>

            {/* Messages */}
            <div
              ref={scrollRef}
              className="flex-1 overflow-y-auto px-3 py-3 space-y-2.5"
              style={{ scrollbarWidth: 'thin' }}
            >
              {messages.length === 0 && (
                <p className="text-xs text-text-muted leading-relaxed">
                  Preguntame lo que quieras sobre esta leccion.
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
            <form onSubmit={handleSubmit} className="flex items-end gap-2 px-3 pb-2.5 pt-1 border-t border-border">
              <textarea
                ref={inputRef}
                onKeyDown={onKeyDown}
                rows={1}
                placeholder="Escribe tu pregunta..."
                disabled={isStreaming}
                className="flex-1 min-h-[32px] max-h-[72px] resize-none rounded-xl bg-bg-subtle px-3 py-1.5 text-sm text-text outline-none placeholder:text-text-muted disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={isStreaming}
                aria-label="Enviar"
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-white disabled:opacity-30 transition-colors"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 12h13" /><path d="M12 5l7 7-7 7" />
                </svg>
              </button>
            </form>
          </motion.div>
        )}
      </AnimatePresence>
    </LayoutGroup>
  )
}
