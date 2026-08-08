import { useEffect, useRef, useState } from 'react'
import { ChatAnswer, ChatInput } from '../../components/chat'
import { ClickableSurface } from '../../components/courses/ClickableSurface'
import { useChat } from '../../api/chat'
import type { ChatGrounding, ChatMessage } from '../../types'

/**
 * What the answer stands on, in one line, in the learner's words.
 *
 * `chunks` and `chunks_fts` get no note, and deliberately share that: both are a
 * located passage with its citation printed right underneath, and whether the
 * passage was found by cosine distance or by Spanish full-text search is a fact
 * about our infrastructure, not about how much the learner should trust the answer.
 * The distinction is still carried on `data-grounding` for tests and debugging.
 *
 * The other two are the ones a person has to be told about — `document` because
 * "it is somewhere in your course material" is a weaker claim than "it is on
 * page 3", and `general` because it is not company material at all.
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
  const bubble = (
    <div
      className={`max-w-[85%] md:max-w-[70%] px-3 md:px-4 py-3 text-sm leading-relaxed ${
        isUser
          ? 'bg-primary text-white rounded-xl rounded-br-sm'
          : 'bg-bg-muted text-text rounded-xl rounded-bl-sm'
      }`}
    >
      {!isUser && <GroundingNote grounding={message.grounding} />}

      {isUser ? (
        <p className="whitespace-pre-line break-words">{message.content}</p>
      ) : (
        <ChatAnswer message={message} />
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
  )

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      {isUser ? bubble : <ClickableSurface nodeId="">{bubble}</ClickableSurface>}
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

  function handleSend() {
    const text = input.trim()
    if (!text || isStreaming) return
    void sendMessage(text)
    setInput('')
  }

  return (
    // No fixed height and no inner scroll: the log grows and the *page* scrolls.
    // It used to be `h-[calc(100vh-50px-48px)]` with an `overflow-y-auto` log, which
    // was a scroll box inside a page that now scrolls on its own — two scrollbars for
    // one conversation. `endRef.scrollIntoView` keeps working; it just moves the page.
    <div className="flex flex-col min-h-[calc(100dvh-82px)] md:min-h-[calc(100dvh-98px)]">
      <div className="mb-4">
        <h2 className="text-xl font-semibold text-text">Chat</h2>
        <p className="text-sm text-text-secondary mt-0.5">Pregunta sobre tus cursos y procedimientos</p>
      </div>

      <div className="flex-1 space-y-4 pb-4">
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

      {/* Sticky, so removing the inner scroll does not bury the composer at the bottom
          of a long conversation. It stays on screen; the messages scroll behind it. */}
      <form
        onSubmit={(e) => { e.preventDefault(); handleSend() }}
        className="sticky bottom-0 py-4 bg-bg"
      >
        <ChatInput
          value={input}
          onChange={setInput}
          onSend={handleSend}
          onStop={cancel}
          isStreaming={isStreaming}
        />
      </form>
    </div>
  )
}
