import { useCallback, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from './client'
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
export function useChat(endpoint: ChatEndpoint = '/chat') {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

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
        generative: endpoint === '/chat/admin',
      }
      setMessages((prev) => [...prev, assistantMsg])
      setIsStreaming(true)

      const controller = new AbortController()
      abortRef.current = controller

      try {
        const res = await fetch(`/api/v1${endpoint}`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text }),
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
                      ? { ...m, citations: [...(m.citations ?? []), ...list] }
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
              } else if (eventType === 'done') {
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
                      'Error al conectar con el asistente. Intentalo de nuevo.',
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
    [endpoint],
  )

  const cancel = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const clear = useCallback(() => {
    setMessages([])
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
