import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { ChatAnswer } from '../../components/chat'
import { useChat } from '../../api/chat'
import type { ChatMessage } from '../../types'

const COMPOSER_MAX_HEIGHT = 200

function Bubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] md:max-w-[70%] px-3 md:px-4 py-3 text-sm leading-relaxed ${
          isUser ? 'bg-primary text-white rounded-2xl rounded-br-sm' : 'bg-bg-muted text-text rounded-2xl rounded-bl-sm'
        }`}
      >
        {!isUser && message.grounding === 'general' && (
          <p className="text-xs text-text-muted mb-1.5" data-grounding="general">
            Conocimiento general: no sale de la documentacion subida
          </p>
        )}

        {isUser ? (
          <p className="whitespace-pre-line break-words">{message.content}</p>
        ) : (
          <ChatAnswer message={message} />
        )}
      </div>
    </div>
  )
}

export function AdminChat() {
  const { messages, sendMessage, cancel, isStreaming } = useChat('/chat/admin')
  const [input, setInput] = useState('')
  const [focused, setFocused] = useState(false)
  const taRef = useRef<HTMLTextAreaElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const atBottomRef = useRef(true)
  const prevCountRef = useRef(0)

  useEffect(() => cancel, [cancel])

  // Auto-scroll: stay pinned to bottom during streaming, don't yank if user scrolled up.
  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    atBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  }

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const isNewMessage = messages.length > prevCountRef.current
    prevCountRef.current = messages.length
    if (isNewMessage || atBottomRef.current) {
      el.scrollTop = el.scrollHeight
      atBottomRef.current = true
    }
  }, [messages])

  // Auto-grow textarea
  useLayoutEffect(() => {
    const el = taRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, COMPOSER_MAX_HEIGHT)}px`
    el.style.overflowY = el.scrollHeight > COMPOSER_MAX_HEIGHT ? 'auto' : 'hidden'
  }, [input])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const text = input.trim()
    if (!text) return
    void sendMessage(text)
    setInput('')
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const active = focused || input.trim().length > 0

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="shrink-0 mb-4">
        <h2 className="text-xl font-semibold text-text">Asistente</h2>
        <p className="text-sm text-text-secondary mt-0.5">Pregunta sobre cursos, empleados o la plataforma</p>
      </div>

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto min-h-0"
      >
        <div className="space-y-4 pb-4">
          {messages.length === 0 && (
            <div className="text-center py-12 px-4">
              <p className="text-sm font-medium text-text">¿En que puedo ayudarte?</p>
              <p className="text-sm text-text-secondary mt-1">Gestion de cursos, empleados y la plataforma.</p>
            </div>
          )}
          {messages.map((msg) => (
            <Bubble key={msg.id} message={msg} />
          ))}
        </div>
      </div>

      <form onSubmit={handleSubmit} className="shrink-0 sticky bottom-0 bg-bg pb-4 pt-2">
        <div style={{ filter: 'url(#skillnet-gooey)' }}>
          <div className="relative flex items-end">
            <textarea
              ref={taRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              rows={1}
              placeholder="Escribe tu consulta..."
              className="min-h-[44px] max-h-[200px] flex-1 resize-none overflow-y-hidden rounded-3xl bg-bg-muted px-4 py-[11px] text-sm leading-normal text-text outline-none placeholder:text-text-muted"
              style={{
                marginRight: active ? 52 : 0,
                transition: 'margin-right 0.5s cubic-bezier(0.32, 0.72, 0, 1)',
              }}
            />
            <div
              style={{
                position: 'absolute',
                right: 0,
                bottom: 0,
                transform: active ? 'translateX(0)' : 'translateX(-4px)',
                transition: 'transform 0.5s cubic-bezier(0.32, 0.72, 0, 1)',
              }}
            >
              <button
                type={isStreaming ? 'button' : 'submit'}
                onClick={isStreaming ? cancel : undefined}
                disabled={!isStreaming && !input.trim()}
                aria-label={isStreaming ? 'Detener' : 'Enviar'}
                className="flex h-11 w-11 items-center justify-center rounded-full bg-bg-muted text-text-muted transition-colors hover:bg-primary hover:text-white disabled:text-text-muted disabled:hover:bg-bg-muted"
              >
                {isStreaming ? (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                    <rect x="6" y="6" width="12" height="12" rx="2" />
                  </svg>
                ) : (
                  <svg
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    style={{
                      opacity: active ? 1 : 0,
                      transition: 'opacity 0.3s ease 0.15s',
                    }}
                  >
                    <path d="M5 12h13" />
                    <path d="M12 5l7 7-7 7" />
                  </svg>
                )}
              </button>
            </div>
          </div>
        </div>

        <svg style={{ position: 'absolute', width: 0, height: 0 }} aria-hidden="true">
          <defs>
            <filter id="skillnet-gooey">
              <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="blur" />
              <feColorMatrix
                in="blur"
                type="matrix"
                values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 20 -9"
                result="gooey"
              />
              <feComposite in="SourceGraphic" in2="gooey" operator="atop" />
            </filter>
          </defs>
        </svg>
      </form>
    </div>
  )
}
