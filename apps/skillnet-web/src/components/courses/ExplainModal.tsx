/**
 * The "Ver mas" modal for click-to-explain (§8.6).
 *
 * Opens when the learner clicks "Ver mas" on an ExplainPopover. Shows the
 * explanation in a scrollable area with clickable words inside it, a navigation
 * stack (breadcrumb + back button) for drilling into terms found in the
 * explanation itself, and a follow-up composer at the bottom that streams
 * answers from the shared tutor at `POST /api/v1/chat`.
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
import { createPortal } from 'react-dom'
import { useIntl } from 'react-intl'
import type { IntlShape } from 'react-intl'
import { ClickableSurface } from './ClickableSurface'
import { ExplainLayer } from './explainLayer'
import { EXPLAIN_LAYER_MODAL } from './explainLayers'
import { UiSpecRenderer } from './UiSpecRenderer'
import { gateProgram } from './kit'
import { ChatInput } from '../chat/ChatInput'
import { ChatMarkdown } from '../chat/ChatMarkdown'

/** Focus-trap candidates inside the card. */
const FOCUSABLE =
  'button, [href], input, textarea, select, [tabindex]:not([tabindex="-1"])'

/**
 * OpenUI Lang always opens with `root = …`. The tutor streams that program as plain
 * `token` events and then emits the compiled tree in a trailing `ui` event; if the
 * `ui` event never lands (layout skipped, connection dropped, program failed the gate),
 * the accumulated tokens are the raw DSL and must NOT be shown as prose. Same guard
 * `ChatAnswer` uses so a generative answer never leaks `root = Stack(...)` as text.
 */
const PROGRAM_DSL = /^\s*root\s*=/

/**
 * The same probe the backend uses to decide an answer *attempted* a program
 * (`_is_genui_candidate`). `PROGRAM_DSL` only catches a program that starts the answer;
 * a model that writes one line of prose first, or fences the program in ``` ``` ``, slips
 * past it and the raw `root = Stack(...)` reaches the reader as text. Anchoring to a line
 * start keeps a sentence that merely mentions the words from being mistaken for code.
 */
const PROGRAM_ANYWHERE = /(?:^|\n)\s*root\s*=\s*Stack\s*\(/

/** A fenced code block wrapper the model sometimes puts around its program. */
const CODE_FENCE = /^\s*```[a-zA-Z]*\n?|```\s*$/g

/**
 * Layout-only atoms of the OpenUI dialect: the `Stack` format, a `TextContent` variant,
 * a `Callout` tone. They are string literals in the program but carry no reader-facing
 * text, so they are dropped when we salvage prose from a program that never rendered.
 */
const DSL_ATOM = new Set([
  'md',
  'lead',
  'body',
  'caption',
  'info',
  'warn',
  'success',
  'danger',
  'explanation',
  'exercise',
])

/** A double-quoted OpenUI Lang string literal, honouring `\"` and `\\` escapes. */
const DSL_LITERAL = /"((?:[^"\\]|\\.)*)"/g

/**
 * Pull the human-readable text out of an OpenUI Lang program. When a program never
 * validates there is no tree to render — but its string literals are the very prose the
 * model wrote (the lead line, the step texts, a callout body), so a failed layout can
 * still degrade to a real plain-text answer instead of an error. Structural atoms (the
 * `"md"` format, a `"lead"` variant, a `"warn"` tone) are dropped so only sentences
 * remain, and the raw `root = Stack(...)` scaffolding never reaches the reader.
 */
function dslToProse(dsl: string): string {
  const parts: string[] = []
  for (const match of dsl.matchAll(DSL_LITERAL)) {
    const text = match[1].replace(/\\(["\\])/g, '$1').trim()
    if (!text || DSL_ATOM.has(text.toLowerCase())) continue
    parts.push(text)
  }
  return parts.join('\n\n')
}

/**
 * The best readable answer to show when no valid program renders. Genuine prose tokens
 * are returned untouched; DSL-shaped tokens (or an invalid program whose `ui` event never
 * validated) are stripped down to the text their literals carry. `""` only when there is
 * genuinely nothing to show, which is the one case that still earns the error message.
 */
function readableAnswer(content: string, program: string | null): string {
  const text = content.replace(CODE_FENCE, '').trim()
  if (text && !PROGRAM_DSL.test(text) && !PROGRAM_ANYWHERE.test(text)) return text
  return dslToProse(text || program || '')
}

// ── The one way an answer becomes pixels ────────────────────────

interface AnswerBodyProps {
  /** Accumulated `token` text. May be raw OpenUI Lang; never rendered as such. */
  content: string
  /** The compiled program from the trailing `ui` event, when it landed. */
  program: string | null
  /** The stream is still open and nothing readable has arrived yet. */
  isLoading: boolean
  /** A message to show instead of an answer. */
  error: string | null
}

/**
 * The first explanation and every follow-up in the thread render through here.
 *
 * They used to each carry their own copy of the fallback chain, and the copies drifted:
 * the follow-up's rendered `null` when nothing was readable, so an answer that arrived
 * empty — a program that failed the backend's validation streams no prose to fall back
 * on — left an empty bubble and read as "the reply never came". One chain now, with one
 * outcome for every case: valid program → blocks; real prose → markdown; error → the
 * error; nothing at all → the retry line. Never blank, never the raw `root = Stack(...)`.
 */
function AnswerBody({ content, program, isLoading, error }: AnswerBodyProps) {
  const intl = useIntl()
  const gate = gateProgram(program)
  const showBlocks = Boolean(program) && !gate.blocked && !gate.empty
  const prose = readableAnswer(content, program)

  if (error) return <p className="text-sm text-danger">{error}</p>
  if (showBlocks) {
    return (
      <UiSpecRenderer
        program={program!}
        nodeId=""
        format="explanation"
        arriving
        className="openui-chat"
      />
    )
  }
  if (isLoading) {
    return (
      <span
        className="typing-dots"
        aria-label={intl.formatMessage({ id: 'explain.generating' })}
      >
        <span /><span /><span />
      </span>
    )
  }
  if (prose) return <ChatMarkdown content={prose} isStreaming={false} />
  return (
    <p className="text-sm text-text-muted">
      {intl.formatMessage({ id: 'explain.errorRetry' })}
    </p>
  )
}

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
  program?: string
  isStreaming?: boolean
  /** Set when the stream failed with nothing readable to show in its place. */
  error?: string
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
}

// ── Icons ───────────────────────────────────────────────────────

function BackIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="15 18 9 12 15 6" />
    </svg>
  )
}

// ── SSE parser for follow-up chat ───────────────────────────────

/**
 * Stream a follow-up question to `POST /api/v1/chat`. Same SSE dialect as
 * the main chat — copied here so the modal does not depend on `useChat`'s
 * message-list state, which is page-level.
 */
async function streamFollowUp(
  intl: IntlShape,
  message: string,
  context: Record<string, unknown>,
  sessionId: string | null,
  signal: AbortSignal,
  onToken: (chunk: string) => void,
  onProgram: (program: string) => void,
  onSessionId: (sessionId: string) => void,
): Promise<void> {
  const res = await fetch('/api/v1/chat', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      context,
      ...(sessionId ? { session_id: sessionId } : {}),
    }),
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
        } else if (eventType === 'ui') {
          onProgram(String(data.program ?? ''))
        } else if (eventType === 'done') {
          const nextSessionId = data.session_id
          if (typeof nextSessionId === 'string' && nextSessionId) {
            onSessionId(nextSessionId)
          }
        } else if (eventType === 'error') {
          throw new Error(
            String(data.detail ?? intl.formatMessage({ id: 'explain.chatError' })),
          )
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
  onSessionId: (sessionId: string) => void
}

/**
 * Mark only the expanded Curio flow for personalized tutor generation. The quick
 * `/explain` glimpse stays shared; this context travels to `/chat`, whose backend loads
 * the real node and the authenticated learner profile rather than trusting profile data
 * from the browser.
 */
function curioChatContext(
  term: string,
  selectionContext: string,
  nodeId: string | null,
  language?: string,
): Record<string, unknown> {
  return {
    surface: 'curio_explain',
    selected_term: term,
    selection_context: selectionContext,
    ...(nodeId ? { node_id: nodeId } : {}),
    ...(language ? { language } : {}),
  }
}

/**
 * Generates a rich OpenUI explanation through the learner tutor endpoint. That route
 * also accepts admins previewing a course, so one surface works for both roles without
 * granting employees access to the organization assistant.
 * Falls back to prose if the model doesn't produce valid OpenUI Lang.
 *
 * It does **not** own a `ClickableSurface`: the modal wraps one around this panel *and*
 * the follow-up thread together, so both are click-to-explain from a single handler
 * (§8.3). When the surface lived in here, only the first explanation was clickable and
 * every follow-up answer was dead text — the same mistake Curio avoids by putting its
 * one handler on the whole scroll area.
 */
function ExplanationPanel({
  term,
  context,
  nodeId,
  language,
  onSessionId,
}: ExplanationPanelProps) {
  const intl = useIntl()
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
      `Elige la redaccion, el orden y la forma que mejor ayuden a entenderlo.` +
      (language ? ` Responde en ${language}.` : '')

    // Stream from the shared tutor endpoint, which can also emit OpenUI Lang.
    ;(async () => {
      try {
        const res = await fetch('/api/v1/chat', {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: prompt,
            context: curioChatContext(term, context, nodeId, language),
          }),
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
                setContent('')  // clear raw tokens so DSL never leaks through the fallback
              } else if (eventType === 'done') {
                const sessionId = data.session_id
                if (
                  typeof sessionId === 'string' &&
                  sessionId &&
                  !controller.signal.aborted
                ) {
                  onSessionId(sessionId)
                }
              }
              eventType = ''
            }
          }
        }
        setIsLoading(false)
      } catch {
        if (controller.signal.aborted) return
        setError(intl.formatMessage({ id: 'explain.error' }))
        setIsLoading(false)
      }
    })()

    return () => controller.abort()
  }, [term, context, nodeId, language, intl, onSessionId])

  // The fallback chain lives in `AnswerBody`, shared with the follow-up thread.
  return (
    <div aria-live="polite">
      <AnswerBody
        content={content}
        program={program}
        isLoading={isLoading}
        error={error}
      />
    </div>
  )
}

// ── Follow-up state (shared between messages display and composer) ──

function useFollowUp(
  term: string,
  selectionContext: string,
  nodeId: string | null,
  initialSessionId: string | null,
  onSessionId: (sessionId: string) => void,
  language?: string,
) {
  const intl = useIntl()
  const [messages, setMessages] = useState<FollowUpMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const sessionIdRef = useRef<string | null>(initialSessionId)

  useEffect(() => () => abortRef.current?.abort(), [])
  useEffect(() => {
    sessionIdRef.current = initialSessionId
  }, [initialSessionId, nodeId, selectionContext, term])

  /**
   * Drop the thread. The follow-up conversation is scoped to the term on screen — after
   * drilling into a word found *inside* an answer, the old exchange is about something
   * else, and leaving it visible seeds the next question with the wrong context.
   */
  const reset = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    sessionIdRef.current = null
    setMessages([])
    setIsStreaming(false)
  }, [])

  const send = useCallback(
    async (text: string) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      const userMsg: FollowUpMessage = { id: crypto.randomUUID(), role: 'user', content: text }
      const assistantId = crypto.randomUUID()
      const assistantMsg: FollowUpMessage = { id: assistantId, role: 'assistant', content: '', isStreaming: true }

      setMessages((prev) => [...prev, userMsg, assistantMsg])
      setIsStreaming(true)

      const seeded = messages.length === 0
        ? `Contexto: estoy leyendo sobre "${term}". Mi pregunta: ${text}`
        : text

      try {
        await streamFollowUp(
          intl,
          seeded,
          curioChatContext(term, selectionContext, nodeId, language),
          sessionIdRef.current,
          controller.signal,
          (chunk) => {
            if (controller.signal.aborted) return
            setMessages((prev) => prev.map((m) => m.id === assistantId ? { ...m, content: m.content + chunk } : m))
          },
          (program) => {
            if (controller.signal.aborted || abortRef.current !== controller) return
            setMessages((prev) => prev.map((m) => m.id === assistantId ? { ...m, program } : m))
          },
          (nextSessionId) => {
            if (controller.signal.aborted || abortRef.current !== controller) return
            sessionIdRef.current = nextSessionId
            onSessionId(nextSessionId)
          },
        )
      } catch (err) {
        // An abort means a newer turn (or a stack move) took over. `reset` clears the
        // thread outright, but `send` aborting the previous stream does not: that message
        // stays on screen, so it must be settled here too. Leaving it `isStreaming` — what
        // the old `return` did, since `finally` then skipped it as well — froze the bubble
        // on the typing dots for the rest of the session.
        const aborted = (err as Error).name === 'AbortError'
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  isStreaming: false,
                  // Only a genuine failure earns the error line; an abort keeps whatever
                  // partial answer it had, and `AnswerBody` decides what that renders as.
                  ...(aborted || m.content
                    ? {}
                    : { error: intl.formatMessage({ id: 'explain.chatError' }) }),
                }
              : m,
          ),
        )
      } finally {
        if (abortRef.current === controller) {
          setIsStreaming(false)
          setMessages((prev) => prev.map((m) => m.id === assistantId ? { ...m, isStreaming: false } : m))
        }
      }
    },
    [intl, language, messages.length, nodeId, onSessionId, selectionContext, term],
  )

  return { messages, isStreaming, send, reset }
}

// Follow-up messages (rendered inside the scrollable area)
function FollowUpMessages({ messages }: { messages: FollowUpMessage[] }) {
  if (messages.length === 0) return null
  return (
    <div className="mt-5 space-y-3 border-t border-border pt-4">
      {messages.map((msg) => (
        <div key={msg.id} className={msg.role === 'user' ? 'text-right' : ''}>
          {msg.role === 'user' ? (
            <span className="inline-block bg-bg-muted px-3 py-1.5 rounded-2xl text-sm text-text">
              {msg.content}
            </span>
          ) : (
            <div className="text-sm">
              <AnswerBody
                content={msg.content}
                program={msg.program ?? null}
                isLoading={Boolean(msg.isStreaming)}
                error={msg.error ?? null}
              />
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// Composer input — outside the scroll, sticky at bottom of the card
function FollowUpInput({
  onSend,
  isStreaming,
}: {
  onSend: (text: string) => void
  isStreaming?: boolean
}) {
  const intl = useIntl()
  const [input, setInput] = useState('')

  function handleSend() {
    const text = input.trim()
    if (!text) return
    onSend(text)
    setInput('')
  }

  return (
    <form onSubmit={(e) => { e.preventDefault(); handleSend() }} className="shrink-0 px-4 pb-4 pt-2">
      <ChatInput
        value={input}
        onChange={setInput}
        onSend={handleSend}
        isStreaming={isStreaming}
        placeholder={intl.formatMessage({ id: 'explain.followUpPlaceholder' })}
        size="sm"
      />
    </form>
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
}: ExplainModalProps) {
  const intl = useIntl()
  const cardRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<HTMLButtonElement>(null)
  const returnFocusTo = useRef<Element | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  const [stack, setStack] = useState<StackEntry[]>([
    { term, context, nodeId },
  ])
  const [initialSession, setInitialSession] = useState<{
    entryKey: string
    sessionId: string
  } | null>(null)

  // Reset the stack when the modal opens with a new term.
  useEffect(() => {
    if (open) {
      setStack([{ term, context, nodeId }])
    }
  }, [open, term, context, nodeId])

  const current = stack[stack.length - 1]
  const currentEntryKey = JSON.stringify([
    current.term,
    current.context,
    current.nodeId,
    stack.length,
  ])
  const sessionId = initialSession?.entryKey === currentEntryKey
    ? initialSession.sessionId
    : null
  const rememberSessionId = useCallback(
    (nextSessionId: string) => {
      setInitialSession({ entryKey: currentEntryKey, sessionId: nextSessionId })
    },
    [currentEntryKey],
  )

  const followUpState = useFollowUp(
    current.term,
    current.context,
    current.nodeId,
    sessionId,
    rememberSessionId,
    language,
  )
  const { reset: resetFollowUp } = followUpState

  // Closing or opening on a different root selection aborts any old stream and drops its
  // session immediately. A late callback is keyed to the old entry and cannot be reused.
  useEffect(() => {
    resetFollowUp()
    setInitialSession(null)
  }, [open, term, context, nodeId, resetFollowUp])

  /** Every stack move drops the follow-up thread and returns to the top of the panel. */
  const rewind = useCallback(() => {
    resetFollowUp()
    setInitialSession(null)
    if (scrollRef.current) scrollRef.current.scrollTop = 0
  }, [resetFollowUp])

  const goBack = useCallback(() => {
    setStack((prev) => (prev.length > 1 ? prev.slice(0, -1) : prev))
    rewind()
  }, [rewind])

  const navigateTo = useCallback(
    (index: number) => {
      setStack((prev) => prev.slice(0, index + 1))
      rewind()
    },
    [rewind],
  )

  const drillDown = useCallback(
    (drillTerm: string, drillContext: string) => {
      setStack((prev) => [...prev, { term: drillTerm, context: drillContext, nodeId }])
      rewind()
    },
    [nodeId, rewind],
  )

  // Follow the thread: a streamed answer that lands below the fold is an answer the
  // learner never sees, and it is also where the popover had nothing to anchor to.
  useEffect(() => {
    if (followUpState.messages.length === 0) return
    const pane = scrollRef.current
    if (pane) pane.scrollTop = pane.scrollHeight
  }, [followUpState.messages])

  /**
   * Escape and the focus trap, both missing before: the card was a `div` that keyboard
   * focus walked straight out of, and the only way out was the mouse.
   *
   * Capture phase, and it yields to an open popover. `ClickableSurface` closes its own
   * selection on a bubble-phase Escape, so checking for a live `.explain-popover` here
   * gives the two layers the order a reader expects — first the bubble, then the modal —
   * without either component having to know the other's state.
   */
  useEffect(() => {
    if (!open) return
    returnFocusTo.current = document.activeElement
    closeRef.current?.focus()

    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') {
        if (document.querySelector('.explain-popover')) return
        event.stopPropagation()
        onClose()
        return
      }
      if (event.key !== 'Tab') return
      const card = cardRef.current
      if (!card) return
      const items = Array.from(card.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => el.offsetParent !== null,
      )
      if (items.length === 0) {
        event.preventDefault()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      const active = document.activeElement
      if (event.shiftKey && (active === first || !card.contains(active))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (active === last || !card.contains(active))) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown, true)
    return () => {
      document.removeEventListener('keydown', onKeyDown, true)
      if (returnFocusTo.current instanceof HTMLElement) returnFocusTo.current.focus()
    }
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    // Everything under here explains at the modal's layer, not the page's, so a popover
    // opened inside the card paints above it instead of behind it.
    <ExplainLayer zIndex={EXPLAIN_LAYER_MODAL}>
      {/* Scrim */}
      <div className="fixed inset-0 z-[100] bg-slate-900/25 backdrop-blur-sm" onClick={onClose} />

      {/* Card */}
      <div className="fixed inset-0 z-[101] flex items-center justify-center p-5 pointer-events-none">
        <div
          ref={cardRef}
          role="dialog"
          aria-modal="true"
          // Distinct from the popover's "Explicacion de X": the two are both dialogs
          // and both on screen at once, so they must not answer to the same name.
          aria-label={intl.formatMessage({ id: 'explain.expandedLabel' }, { term: current.term })}
          className="pointer-events-auto flex flex-col w-full max-w-[560px] bg-bg border border-border overflow-hidden"
          style={{ maxHeight: 'min(80vh, 640px)', borderRadius: 16 }}
        >
          {/* Header */}
          <header className="flex shrink-0 items-center gap-2 px-5 pb-1 pt-4">
            {stack.length > 1 && (
              <button
                type="button"
                onClick={goBack}
                aria-label={intl.formatMessage({ id: 'explain.back' })}
                className="shrink-0 p-1 text-text-muted hover:text-text transition-colors"
              >
                <BackIcon />
              </button>
            )}
            <h2 className="flex-1 text-lg font-semibold leading-snug text-text truncate">
              {current.term}
            </h2>
            <button
              ref={closeRef}
              onClick={onClose}
              aria-label={intl.formatMessage({ id: 'explain.close' })}
              className="shrink-0 p-1 text-xl leading-none text-text-muted hover:text-text transition-colors"
            >
              &times;
            </button>
          </header>

          {/* Breadcrumb */}
          {stack.length > 1 && (
            <div className="flex items-center gap-1 px-5 pb-1 text-xs text-text-muted overflow-x-auto" style={{ scrollbarWidth: 'none' }}>
              {stack.map((entry, i) => (
                <span key={i} className="flex items-center gap-1 shrink-0">
                  {i > 0 && <span className="text-text-muted/50">›</span>}
                  <button
                    type="button"
                    onClick={() => navigateTo(i)}
                    className={`transition-colors hover:text-text ${i === stack.length - 1 ? 'text-text font-medium' : ''}`}
                  >
                    {entry.term}
                  </button>
                </span>
              ))}
            </div>
          )}

          {/* Scrollable content. ONE ClickableSurface over the explanation *and* the
              follow-up thread, so a word is clickable wherever it appears — the panel,
              a generated block, or an answer that arrived thirty seconds later. */}
          <div
            ref={scrollRef}
            className="min-h-0 flex-1 overflow-y-auto px-5 py-4 text-sm leading-relaxed text-text"
            style={{ scrollbarWidth: 'none' }}
          >
            <ClickableSurface
              nodeId={current.nodeId}
              language={language}
              skipTerm={current.term}
              onVerMas={drillDown}
            >
              <ExplanationPanel
                key={`${current.term}-${stack.length}`}
                term={current.term}
                context={current.context}
                nodeId={current.nodeId}
                language={language}
                onSessionId={rememberSessionId}
              />

              <FollowUpMessages messages={followUpState.messages} />
            </ClickableSurface>
          </div>

          {/* The composer only exists once the initial generation has completed. A
              disabled input during loading looked like a broken attempt to type. */}
          {sessionId && (
            <FollowUpInput
              onSend={followUpState.send}
              isStreaming={followUpState.isStreaming}
            />
          )}
        </div>
      </div>
    </ExplainLayer>,
    document.body,
  )
}
