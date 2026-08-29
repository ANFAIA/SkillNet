import { useCallback, useRef, useState } from 'react'
import { useIntl } from 'react-intl'
import { useQuery } from '@tanstack/react-query'
import { get } from './client'
import { executeTool } from '../lib/toolRegistry'
import type {
  ChatGrounding,
  ChatMessage,
  ChatMessageRead,
  ChatSessionRead,
  Citation,
} from '../types'

/**
 * Which assistant answers — and nothing else. The two endpoints speak the *same* SSE
 * dialect, so there is deliberately one parser below rather than a branch: `ui`
 * included, now that `_should_lay_out` lays out `admin` turns too. A second handler
 * for the admin stream is how the `ui` event would get silently dropped on one surface.
 */
type ChatEndpoint = '/chat' | '/chat/admin'

/** Extra context sent on the first message only (e.g. node title/summary for lesson chat). */
export type ChatContext = Record<string, unknown>

/**
 * Chat streams over `fetch` + `ReadableStream` (not EventSource) so we can POST
 * the message body and cancel cleanly with an AbortController.
 *
 * ## The stream does not end at `done`
 *
 * `done` means *the answer is complete*: the bubble stops blinking and the input
 * re-enables right there, which is the moment the learner cares about. The server
 * may then keep the connection open for one more beat to send a `ui` event with
 * the same answer laid out in blocks. Two consequences, both deliberate:
 *
 * - `isStreaming` is cleared on `done`, not when the reader drains. Waiting for
 *   the reader would leave the composer disabled through the layout call, which
 *   is precisely the "chat got slower" regression the design refuses to pay.
 * - The loop keeps reading afterwards. A layout that fails sends
 *   `layout_skipped` and nothing changes; the prose is the answer either way.
 */
export interface UseChatOptions {
  /**
   * Render with the "reveal at once" pattern: dots for the whole generation, then the
   * final answer (OpenUI blocks, or prose if layout was skipped) in one go — no visible
   * token stream that later re-renders into blocks. Defaults to `true` for the admin
   * endpoint. The lesson tutor sets it too, so its two-phase (prose → layout) answer
   * does not flash the prose before the blocks.
   */
  generative?: boolean
}

export function useChat(
  endpoint: ChatEndpoint = '/chat',
  firstMessageContext?: ChatContext,
  options?: UseChatOptions,
) {
  // `useChat` is a hook, so the copy it owns is resolved the same way a component's is.
  // There is no second mechanism for "text from a module under `api/`": whatever needs a
  // message is either a hook or is handed an `IntlShape` (`lib/capabilityCopy.ts`).
  const intl = useIntl()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const sentCountRef = useRef(0)
  // The server creates a session on the first turn and reports its id on `done`. We keep
  // it here and send it on every later turn so they land on the SAME session — which is
  // what lets the tutor load the conversation's recent history and answer follow-ups
  // ("vale pero qué pasos debo seguir") against the ongoing thread instead of near-blind.
  const sessionIdRef = useRef<string | null>(null)
  // Derived to a stable boolean so a fresh `options` object each render does not churn
  // the `sendMessage` callback identity.
  const generativeMode = options?.generative ?? endpoint === '/chat/admin'

  const sendMessage = useCallback(
    async (text: string) => {
      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text,
      }
      setMessages((prev) => [...prev, userMsg])

      const assistantId = crypto.randomUUID()
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        citations: [],
        isStreaming: true,
        generative: generativeMode,
      }
      setMessages((prev) => [...prev, assistantMsg])
      setIsStreaming(true)

      const controller = new AbortController()
      abortRef.current = controller

      try {
        // Send context only on the first message so the backend can ground the
        // conversation without polluting the session title.
        const isFirst = sentCountRef.current === 0
        sentCountRef.current += 1
        const payload: Record<string, unknown> = { message: text }
        if (isFirst && firstMessageContext) payload.context = firstMessageContext
        // Thread every turn after the first onto the session the server opened, so the
        // tutor carries the conversation's memory.
        if (sessionIdRef.current) payload.session_id = sessionIdRef.current

        const res = await fetch(`/api/v1${endpoint}`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
          signal: controller.signal,
        })

        if (!res.ok || !res.body) {
          throw new Error(`Chat request failed: ${res.status}`)
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let eventType = ''

        while (true) {
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
                data = JSON.parse(raw)
              } catch {
                continue
              }

              if (eventType === 'token') {
                const chunk = String(data.content ?? '')
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId ? { ...m, content: m.content + chunk } : m,
                  ),
                )
              } else if (eventType === 'citations') {
                const list = (data.citations ?? []) as Citation[]
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? {
                          ...m,
                          citations: list,
                          ...(typeof data.content === 'string' ? { content: data.content } : {}),
                        }
                      : m,
                  ),
                )
              } else if (eventType === 'suggestions') {
                const prompts = (data.prompts ?? []) as string[]
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId ? { ...m, suggestions: prompts } : m,
                  ),
                )
              } else if (eventType === 'grounding') {
                const grounding = data.grounding as ChatGrounding
                setMessages((prev) =>
                  prev.map((m) => (m.id === assistantId ? { ...m, grounding } : m)),
                )
              } else if (eventType === 'layout_start') {
                setMessages((prev) =>
                  prev.map((m) => (m.id === assistantId ? { ...m, isLayingOut: true } : m)),
                )
              } else if (eventType === 'layout_skipped') {
                setMessages((prev) =>
                  prev.map((m) => (m.id === assistantId ? { ...m, isLayingOut: false } : m)),
                )
              } else if (eventType === 'ui') {
                const program = String(data.program ?? '')
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, program: program || undefined, isLayingOut: false }
                      : m,
                  ),
                )
              } else if (eventType === 'action') {
                const tool = String(data.tool ?? '')
                const args = (data.args ?? {}) as Record<string, unknown>
                if (tool) executeTool(tool, args)
              } else if (eventType === 'done') {
                // Remember the session so the next turn threads onto it (memory).
                const sid = data.session_id
                if (typeof sid === 'string' && sid) sessionIdRef.current = sid
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId ? { ...m, isStreaming: false } : m,
                  ),
                )
                // The answer is complete: give the composer back now, and keep
                // reading for a trailing `ui` event on the same connection.
                if (abortRef.current === controller) setIsStreaming(false)
              } else if (eventType === 'error') {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: String(data.detail ?? 'Error'), isStreaming: false }
                      : m,
                  ),
                )
              }
              // An event type no branch claims falls straight through, on purpose:
              // `org_data` ships on admin turns today and costs the browser nothing
              // until somebody decides what, if anything, it should look like.

              eventType = ''
            }
          }
        }

        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, isStreaming: false, isLayingOut: false } : m,
          ),
        )
      } catch (err) {
        if ((err as Error).name === 'AbortError') {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, isStreaming: false, isLayingOut: false } : m,
            ),
          )
        } else {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    content:
                      m.content ||
                      intl.formatMessage({ id: 'chat.connectionError' }),
                    isStreaming: false,
                    isLayingOut: false,
                  }
                : m,
            ),
          )
        }
      } finally {
        // Only the newest send owns the composer. A trailing `ui` event from the
        // previous turn must not re-enable an input the current turn disabled.
        if (abortRef.current === controller) {
          setIsStreaming(false)
          abortRef.current = null
        }
      }
    },
    [endpoint, firstMessageContext, generativeMode, intl],
  )

  const cancel = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const clear = useCallback(() => {
    setMessages([])
    // A cleared thread is a new conversation: drop the session so the next message opens
    // a fresh one instead of appending to the old memory.
    sessionIdRef.current = null
    sentCountRef.current = 0
  }, [])

  return { messages, sendMessage, cancel, clear, isStreaming }
}

export function useChatSessions() {
  return useQuery({
    queryKey: ['chat', 'sessions'],
    queryFn: () => get<ChatSessionRead[]>('/chat/sessions'),
  })
}

export function useChatSessionMessages(sessionId: string | undefined) {
  return useQuery({
    queryKey: ['chat', 'sessions', sessionId, 'messages'],
    queryFn: () => get<ChatMessageRead[]>(`/chat/sessions/${sessionId}/messages`),
    enabled: !!sessionId,
  })
}
