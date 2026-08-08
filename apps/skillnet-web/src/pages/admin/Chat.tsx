import { useEffect, useRef, useState } from 'react'
import { useIntl } from 'react-intl'
import { ChatAnswer, ChatInput } from '../../components/chat'
import { useChat } from '../../api/chat'
import type { ChatMessage } from '../../types'

function Bubble({ message }: { message: ChatMessage }) {
  const intl = useIntl()
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
            {intl.formatMessage({ id: 'chat.grounding' })}
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
  const intl = useIntl()
  const { messages, sendMessage, cancel, isStreaming } = useChat('/chat/admin')
  const [input, setInput] = useState('')
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

  function handleSend() {
    const text = input.trim()
    if (!text) return
    void sendMessage(text)
    setInput('')
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="shrink-0 mb-4">
        <h2 className="text-xl font-semibold text-text">{intl.formatMessage({ id: 'chat.title' })}</h2>
        <p className="text-sm text-text-secondary mt-0.5">{intl.formatMessage({ id: 'chat.subtitle' })}</p>
      </div>

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto min-h-0"
      >
        <div className="space-y-4 pb-4">
          {messages.length === 0 && (
            <div className="text-center py-12 px-4">
              <p className="text-sm font-medium text-text">{intl.formatMessage({ id: 'chat.emptyTitle' })}</p>
              <p className="text-sm text-text-secondary mt-1">{intl.formatMessage({ id: 'chat.emptySubtitle' })}</p>
            </div>
          )}
          {messages.map((msg) => (
            <Bubble key={msg.id} message={msg} />
          ))}
        </div>
      </div>

      <form onSubmit={(e) => { e.preventDefault(); handleSend() }} className="shrink-0 sticky bottom-0 bg-bg pb-4 pt-2">
        <ChatInput
          value={input}
          onChange={setInput}
          onSend={handleSend}
          onStop={cancel}
          isStreaming={isStreaming}
          placeholder={intl.formatMessage({ id: 'chat.placeholder' })}
        />
      </form>
    </div>
  )
}
