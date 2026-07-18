import { useCallback, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from './client'
import type { ChatMessage, ChatMessageRead, ChatSessionRead, Citation } from '../types'

type ChatEndpoint = '/chat' | '/chat/admin'

// Chat streams over `fetch` + `ReadableStream` (not EventSource) so we can POST
// the message body and cancel cleanly with an AbortController.
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
              } else if (eventType === 'done') {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId ? { ...m, isStreaming: false } : m,
                  ),
                )
              } else if (eventType === 'error') {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: String(data.detail ?? 'Error'), isStreaming: false }
                      : m,
                  ),
                )
              }

              eventType = ''
            }
          }
        }

        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m)),
        )
      } catch (err) {
        if ((err as Error).name === 'AbortError') {
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, isStreaming: false } : m)),
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
                  }
                : m,
            ),
          )
        }
      } finally {
        setIsStreaming(false)
        abortRef.current = null
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
