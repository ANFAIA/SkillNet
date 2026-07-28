import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Button } from '../../components/ui'
import { ChatAnswer } from '../../components/chat'
import { useChat } from '../../api/chat'
import type { ChatMessage } from '../../types'

function SendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}

function Bubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] md:max-w-[70%] px-3 md:px-4 py-3 text-sm leading-relaxed ${
          isUser ? 'bg-primary text-white rounded-xl rounded-br-sm' : 'bg-bg-muted text-text rounded-xl rounded-bl-sm'
        }`}
      >
        {/* Same honesty note as the employee tutor, same reason. */}
        {!isUser && message.grounding === 'general' && (
          <p className="text-xs text-text-muted mb-1.5" data-grounding="general">
            Conocimiento general: no sale de la documentacion subida
          </p>
        )}

        {/*
          What the admin typed is what the admin typed: no markdown pass over the
          user's own bubble. `ChatAnswer` owns the assistant side, and it is the very
          same component the tutor uses — blocks when a program arrives and clears the
          browser's gate, the streamed prose otherwise, never both.

          This used to be `ChatMarkdown` directly, on the grounds that the admin
          assistant answers in two operational lines. `_should_lay_out` in
          `chat_service.py` now lays out `admin` turns too, because the question this
          surface exists for — "como van mis empleados" — is five people and four
          columns, which is a table everywhere else an administrator works. The two
          switches and the fall back to prose are unchanged; only the exclusion went.
        */}
        {isUser ? (
          <p className="whitespace-pre-line break-words">{message.content}</p>
        ) : (
          <ChatAnswer message={message} />
        )}

        {/* The second beat is now reachable here, so it has to be visible here too:
            `done` returns the composer while the layout call is still running. */}
        {message.isLayingOut && (
          <p className="text-xs text-text-muted mt-2">Dando formato...</p>
        )}
      </div>
    </div>
  )
}

export function AdminChat() {
  const { messages, sendMessage, cancel, isStreaming } = useChat('/chat/admin')
  const [input, setInput] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => cancel, [cancel])
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const text = input.trim()
    if (!text || isStreaming) return
    void sendMessage(text)
    setInput('')
  }

  return (
    // No inner scroll — see the note in the employee Chat. The log grows, the page
    // scrolls, and the composer below stays put.
    <div className="flex flex-col min-h-[calc(100dvh-82px)] md:min-h-[calc(100dvh-98px)]">
      <div className="mb-4">
        <h2 className="text-xl font-semibold text-text">Asistente</h2>
        <p className="text-sm text-text-secondary mt-0.5">Pregunta sobre cursos, empleados o la plataforma</p>
      </div>

      <div className="flex-1 space-y-4 pb-4">
        {messages.length === 0 && (
          <div className="text-center py-12 px-4">
            <p className="text-sm font-medium text-text">¿En que puedo ayudarte?</p>
            <p className="text-sm text-text-secondary mt-1">Gestion de cursos, empleados y la plataforma.</p>
          </div>
        )}
        {messages.map((msg) => (
          <Bubble key={msg.id} message={msg} />
        ))}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={handleSubmit}
        className="sticky bottom-0 flex gap-2 py-4 border-t border-border bg-bg"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Escribe tu consulta..."
          disabled={isStreaming}
          className="flex-1 px-3 py-2 text-sm text-text border border-border rounded-lg bg-bg placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors disabled:opacity-50"
        />
        {isStreaming ? (
          <Button type="button" variant="secondary" size="md" onClick={cancel}>Detener</Button>
        ) : (
          <Button type="submit" size="md" disabled={!input.trim()}>
            <SendIcon />
          </Button>
        )}
      </form>
    </div>
  )
}
