/**
 * The "Ver mas" modal for click-to-explain (§8.6).
 *
 * Opens when the learner clicks "Ver mas" on an ExplainPopover. Shows the
 * explanation in a scrollable area with clickable words inside it, a navigation
 * stack (breadcrumb + back button) for drilling into terms found in the
 * explanation itself, and a follow-up composer at the bottom that streams
 * answers from `POST /api/v1/chat/admin`.
 *
 * Inspired by Curio's DescribeModal but adapted to SkillNet's design tokens
 * and existing infrastructure.
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react'
import type { FormEvent } from 'react'
import { Modal } from '../ui/Modal'
import { ClickableSurface } from './ClickableSurface'
import { UiSpecRenderer } from './UiSpecRenderer'
import { gateProgram } from './kit'
import { ChatMarkdown } from '../chat/ChatMarkdown'

// ── Types ───────────────────────────────────────────────────────

interface StackEntry {
  term: string
  context: string
  nodeId: string | null
}

interface FollowUpMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  isStreaming?: boolean
}

export interface ExplainModalProps {
  /** The term that was clicked to open the modal. */
  term: string
  /** Block context around the term. */
  context: string
  /** Node the term belongs to. */
  nodeId: string | null
  /** Language hint for the explanation. */
  language?: string
  /** Whether the modal is open. */
  open: boolean
  /** Called when the modal should close. */
  onClose: () => void
  /** Rect of the element that opened the modal, for FLIP animation. */
  origin?: DOMRect | null
}

// ── Icons ───────────────────────────────────────────────────────

function BackIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="15 18 9 12 15 6" />
    </svg>
  )
}

function SendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}

// ── SSE parser for follow-up chat ───────────────────────────────

/**
 * Stream a follow-up question to `POST /api/v1/chat/admin`. Same SSE dialect as
 * the main chat — copied here so the modal does not depend on `useChat`'s
 * message-list state, which is page-level.
 */
async function streamFollowUp(
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

  if (!res.ok || !res.body) {
    throw new Error(`Chat request failed: ${res.status}`)
  }

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
        let data: Record<string, unknown>
        try {
          data = JSON.parse(raw) as Record<string, unknown>
        } catch {
          continue
        }

        if (eventType === 'token') {
          onToken(String(data.content ?? ''))
        } else if (eventType === 'error') {
          throw new Error(String(data.detail ?? 'Error en la conversacion'))
        }
        eventType = ''
      }
    }
  }
}

// ── Explanation panel (one stack entry) ──────────────────────────

interface ExplanationPanelProps {
  term: string
  context: string
  nodeId: string | null
  language?: string
  onDrillDown: (term: string, context: string) => void
}

/**
 * Generates a rich OpenUI explanation for a term via the chat admin endpoint.
 * Falls back to prose if the model doesn't produce valid OpenUI Lang.
 */
function ExplanationPanel({
  term,
  context,
  nodeId,
  language,
  onDrillDown,
}: ExplanationPanelProps) {
  const [content, setContent] = useState('')
  const [program, setProgram] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setContent('')
    setProgram(null)
    setIsLoading(true)
    setError(null)

    const prompt = `Explicame "${term}" en el contexto de: "${context}". ` +
      `Hazlo visual y claro, con ejemplos si ayudan.` +
      (language ? ` Responde en ${language}.` : '')

    // Stream from the chat admin endpoint which generates OpenUI Lang directly
    ;(async () => {
      try {
        const res = await fetch('/api/v1/chat/admin', {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: prompt }),
          signal: controller.signal,
        })
        if (!res.ok || !res.body) throw new Error(`${res.status}`)

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let eventType = ''
        let tokens = ''

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
              let data: Record<string, unknown>
              try { data = JSON.parse(raw) } catch { continue }

              if (eventType === 'token') {
                tokens += String(data.content ?? '')
                setContent(tokens)
              } else if (eventType === 'ui') {
                setProgram(String(data.program ?? ''))
              }
              eventType = ''
            }
          }
        }
        setIsLoading(false)
      } catch (err) {
        if (controller.signal.aborted) return
        setError('No se pudo generar la explicacion.')
        setIsLoading(false)
      }
    })()

    return () => controller.abort()
  }, [term, context, language])

  // Check if we got a valid program
  const gate = gateProgram(program)
  const showBlocks = Boolean(program) && !gate.blocked && !gate.empty

  const body = error ? (
    <p className="text-sm text-danger">{error}</p>
  ) : showBlocks ? (
    <UiSpecRenderer program={program!} nodeId="" format="explanation" arriving />
  ) : isLoading ? (
    <span className="typing-dots" aria-label="Generando explicacion">
      <span /><span /><span />
    </span>
  ) : content ? (
    <ChatMarkdown content={content} isStreaming={false} />
  ) : (
    <p className="text-sm text-text-muted">Sin contenido.</p>
  )

  return (
    <ClickableSurface
      nodeId={nodeId}
      language={language}
      onVerMas={(drillTerm, drillContext) => onDrillDown(drillTerm, drillContext)}
    >
      <div aria-live="polite">{body}</div>
    </ClickableSurface>
  )
}

// ── Follow-up conversation ──────────────────────────────────────

interface FollowUpProps {
  /** Seed context for the conversation. */
  termContext: string
}

function FollowUp({ termContext }: FollowUpProps) {
  const [messages, setMessages] = useState<FollowUpMessage[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  // Cancel in-flight request on unmount.
  useEffect(() => () => abortRef.current?.abort(), [])

  // Auto-scroll to the latest message.
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages])

  const send = useCallback(
    async (text: string) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      const userMsg: FollowUpMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text,
      }

      const assistantId = crypto.randomUUID()
      const assistantMsg: FollowUpMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        isStreaming: true,
      }

      setMessages((prev) => [...prev, userMsg, assistantMsg])
      setIsStreaming(true)

      // Prefix with term context so the model knows what we are talking about.
      const seeded = messages.length === 0
        ? `Contexto: estoy leyendo sobre "${termContext}". Mi pregunta: ${text}`
        : text

      try {
        await streamFollowUp(seeded, controller.signal, (chunk) => {
          if (controller.signal.aborted) return
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: m.content + chunk } : m,
            ),
          )
        })
      } catch (err) {
        if ((err as Error).name === 'AbortError') return
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: m.content || 'Error al conectar con el asistente.',
                  isStreaming: false,
                }
              : m,
          ),
        )
      } finally {
        if (abortRef.current === controller) {
          setIsStreaming(false)
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, isStreaming: false } : m,
            ),
          )
        }
      }
    },
    [messages.length, termContext],
  )

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const text = input.trim()
    if (!text || isStreaming) return
    void send(text)
    setInput('')
  }

  return (
    <div className="mt-4 border-t border-border pt-4">
      {messages.length > 0 && (
        <div className="space-y-3 mb-3 max-h-64 overflow-y-auto">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`text-sm ${
                msg.role === 'user'
                  ? 'text-right'
                  : 'text-left'
              }`}
            >
              {msg.role === 'user' ? (
                <span className="inline-block bg-primary text-white px-3 py-1.5 rounded-xl rounded-br-sm max-w-[85%]">
                  {msg.content}
                </span>
              ) : (
                <div className="bg-bg-muted px-3 py-2 rounded-xl rounded-bl-sm max-w-[85%] inline-block text-left">
                  <ChatMarkdown content={msg.content} isStreaming={msg.isStreaming} />
                </div>
              )}
            </div>
          ))}
          <div ref={endRef} />
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Pregunta algo mas..."
          disabled={isStreaming}
          className="flex-1 px-3 py-2 text-sm text-text border border-border rounded-lg bg-bg placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!input.trim() || isStreaming}
          className="px-3 py-2 bg-primary text-white rounded-lg text-sm font-medium disabled:opacity-50 hover:opacity-90 transition-opacity flex items-center justify-center"
        >
          <SendIcon />
        </button>
      </form>
    </div>
  )
}

// ── Breadcrumb ──────────────────────────────────────────────────

interface BreadcrumbProps {
  stack: StackEntry[]
  onNavigate: (index: number) => void
}

function Breadcrumb({ stack, onNavigate }: BreadcrumbProps) {
  if (stack.length <= 1) return null

  return (
    <nav className="flex items-center gap-1 text-xs text-text-muted mb-2 flex-wrap" aria-label="Historial de terminos">
      {stack.map((entry, i) => {
        const isLast = i === stack.length - 1
        return (
          <span key={i} className="flex items-center gap-1">
            {i > 0 && <span aria-hidden="true">/</span>}
            {isLast ? (
              <span className="text-text font-medium">{entry.term}</span>
            ) : (
              <button
                type="button"
                onClick={() => onNavigate(i)}
                className="hover:text-primary hover:underline transition-colors"
              >
                {entry.term}
              </button>
            )}
          </span>
        )
      })}
    </nav>
  )
}

// ── Main modal ──────────────────────────────────────────────────

export function ExplainModal({
  term,
  context,
  nodeId,
  language,
  open,
  onClose,
  origin,
}: ExplainModalProps) {
  const [stack, setStack] = useState<StackEntry[]>([
    { term, context, nodeId },
  ])

  // Reset the stack when the modal opens with a new term.
  useEffect(() => {
    if (open) {
      setStack([{ term, context, nodeId }])
    }
  }, [open, term, context, nodeId])

  const current = stack[stack.length - 1]

  const goBack = useCallback(() => {
    setStack((prev) => (prev.length > 1 ? prev.slice(0, -1) : prev))
  }, [])

  const navigateTo = useCallback((index: number) => {
    setStack((prev) => prev.slice(0, index + 1))
  }, [])

  const drillDown = useCallback(
    (drillTerm: string, drillContext: string) => {
      setStack((prev) => [...prev, { term: drillTerm, context: drillContext, nodeId }])
    },
    [nodeId],
  )

  return (
    <Modal open={open} onClose={onClose} size="md" origin={origin} hideClose>
      {/* Header */}
      <div className="flex items-start gap-2 mb-4">
        {stack.length > 1 && (
          <button
            type="button"
            onClick={goBack}
            aria-label="Volver al termino anterior"
            className="mt-0.5 w-7 h-7 flex items-center justify-center rounded-full text-text-muted hover:text-text hover:bg-bg-muted transition-colors shrink-0"
          >
            <BackIcon />
          </button>
        )}
        <div className="flex-1 min-w-0">
          <Breadcrumb stack={stack} onNavigate={navigateTo} />
          <h2 className="text-base font-semibold text-text break-words">
            {current.term}
          </h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Cerrar"
          className="w-8 h-8 flex items-center justify-center rounded-full text-text-muted hover:text-text hover:bg-bg-muted transition-colors shrink-0"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>

      {/* Explanation content — scrollable area with clickable words */}
      <div className="max-h-80 overflow-y-auto mb-2">
        <ExplanationPanel
          key={`${current.term}-${stack.length}`}
          term={current.term}
          context={current.context}
          nodeId={current.nodeId}
          language={language}
          onDrillDown={drillDown}
        />
      </div>

      {/* Follow-up conversation */}
      <FollowUp termContext={current.term} />
    </Modal>
  )
}
