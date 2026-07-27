import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Button } from '../../components/ui'
import { UiSpecRenderer } from '../../components/courses/UiSpecRenderer'
import { useChat } from '../../api/chat'
import type { ChatGrounding, ChatMessage } from '../../types'

function SendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}

/**
 * What the answer stands on, in one line, in the learner's words.
 *
 * `chunks` gets no note: a cited passage is the normal case and the citations are
 * printed right underneath. The other two are the ones a person has to be told
 * about — `document` because "it is somewhere in your course material" is a
 * weaker claim than "it is on page 3", and `general` because it is not company
 * material at all.
 */
const GROUNDING_LABEL: Partial<Record<ChatGrounding, string>> = {
  document: 'De la documentacion de tus cursos, leida entera',
  general: 'Conocimiento general: esto no esta en la documentacion de tu empresa',
}

function GroundingNote({ grounding }: { grounding?: ChatGrounding }) {
  const label = grounding ? GROUNDING_LABEL[grounding] : undefined
  if (!label) return null
  return (
    <p className="text-xs text-text-muted mb-1.5" data-grounding={grounding}>
      {label}
    </p>
  )
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] md:max-w-[70%] px-3 md:px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? 'bg-primary text-white rounded-xl rounded-br-sm'
            : 'bg-bg-muted text-text rounded-xl rounded-bl-sm'
        }`}
      >
        {!isUser && <GroundingNote grounding={message.grounding} />}

        {/*
          The blocks replace the prose only once there is a program, and the prose
          is what comes back if there never is one. `UiSpecRenderer` returns null
          for a blocked or empty program, so rendering the two alternatives (rather
          than the blocks stacked on top of the text) is what would risk an empty
          bubble — hence the program is only chosen when the server sent one, and
          the server only sends one that already parsed into a valid `UISpec`.
        */}
        {message.program ? (
          <UiSpecRenderer program={message.program} nodeId="" format="explanation" />
        ) : (
          <p className="whitespace-pre-line break-words">
            {message.content}
            {message.isStreaming && !message.content && (
              <span className="text-text-muted">Escribiendo...</span>
            )}
            {message.isStreaming && message.content && (
              <span className="inline-block w-1.5 h-4 ml-0.5 align-middle bg-current opacity-60 animate-pulse" />
            )}
          </p>
        )}

        {message.isLayingOut && (
          <p className="text-xs text-text-muted mt-2">Dando formato...</p>
        )}

        {message.citations && message.citations.length > 0 && (
          <div className="mt-2 space-y-0.5">
            {message.citations.map((c, i) => (
              <p key={i} className={`text-xs ${isUser ? 'text-white/60' : 'text-text-muted'}`}>
                {c.document}
                {c.section ? ` · ${c.section}` : ''}
                {c.page ? ` (p.${c.page})` : ''}
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export function Chat() {
  const { messages, sendMessage, cancel, isStreaming } = useChat('/chat')
  const [input, setInput] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  // Cancel any in-flight stream when leaving the page.
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
    <div className="flex flex-col h-[calc(100vh-50px-48px)]">
      <div className="mb-4">
        <h2 className="text-xl font-semibold text-text">Chat</h2>
        <p className="text-sm text-text-secondary mt-0.5">Pregunta sobre tus cursos y procedimientos</p>
      </div>

      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.length === 0 && (
          <div className="text-center py-12 px-4">
            <p className="text-sm font-medium text-text">Hazme una pregunta</p>
            <p className="text-sm text-text-secondary mt-1">
              Puedo ayudarte con cualquier tema de tus cursos y procedimientos.
            </p>
          </div>
        )}
        {messages.map((msg) => (
          <ChatBubble key={msg.id} message={msg} />
        ))}
        <div ref={endRef} />
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2 pt-4 border-t border-border">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Escribe tu pregunta..."
          disabled={isStreaming}
          className="flex-1 px-3 py-2 text-sm text-text border border-border rounded-lg bg-bg placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors disabled:opacity-50"
        />
        {isStreaming ? (
          <Button type="button" variant="secondary" size="md" onClick={cancel}>
            Detener
          </Button>
        ) : (
          <Button type="submit" size="md" disabled={!input.trim()}>
            <SendIcon />
          </Button>
        )}
      </form>
    </div>
  )
}
