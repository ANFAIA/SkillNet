/**
 * NodeChat — clean chat interface for the NodeView sidebar panel.
 *
 * Uses the learner chat endpoint (`/chat`) with node context on the first
 * message so the tutor knows which lesson the learner is looking at.
 * This is a normal message list + input, NOT the floating spider bubble.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useIntl } from 'react-intl'
import { ChatInput } from '../chat/ChatInput'
import { ChatMarkdown } from '../chat/ChatMarkdown'
import { useChat } from '../../api/chat'
import type { ChatContext } from '../../api/chat'
import type { ChatMessage } from '../../types'

export interface NodeChatProps {
  nodeTitle?: string
  nodeSummary?: string
}

function Bubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[90%] px-3 py-2 text-sm leading-relaxed ${
          isUser
            ? 'bg-primary/10 text-text rounded-2xl rounded-br-sm'
            : 'text-text'
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-line break-words">{message.content}</p>
        ) : (
          <>
            <ChatMarkdown content={message.content} isStreaming={message.isStreaming} />
            {message.isStreaming && !message.content && (
              <span className="typing-dots"><span /><span /><span /></span>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export function NodeChat({ nodeTitle, nodeSummary }: NodeChatProps) {
  const intl = useIntl()
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const atBottomRef = useRef(true)
  const prevCountRef = useRef(0)

  // Context sent only on the first message — stabilised by useMemo so
  // useChat's dependency does not churn on every render.
  const context: ChatContext | undefined = useMemo(
    () =>
      nodeTitle
        ? { nodeTitle, nodeSummary: nodeSummary ?? '' }
        : undefined,
    [nodeTitle, nodeSummary],
  )

  const { messages, sendMessage, cancel, isStreaming } = useChat('/chat', context)

  // Cancel any in-flight stream on unmount.
  useEffect(() => cancel, [cancel])

  // Auto-scroll: stay pinned during streaming, leave the user alone if they scrolled up.
  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    atBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60
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
    if (!text || isStreaming) return
    void sendMessage(text)
    setInput('')
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Messages */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto min-h-0 space-y-3 pb-2"
        style={{ scrollbarWidth: 'thin' }}
      >
        {messages.length === 0 && (
          <p className="text-xs text-text-muted py-4">
            {intl.formatMessage({ id: 'nodeChat.empty' })}
          </p>
        )}
        {messages.map((msg) => (
          <Bubble key={msg.id} message={msg} />
        ))}
      </div>

      {/* Composer */}
      <form onSubmit={(e) => { e.preventDefault(); handleSend() }} className="shrink-0 pt-2 border-t border-border">
        <ChatInput
          value={input}
          onChange={setInput}
          onSend={handleSend}
          onStop={cancel}
          isStreaming={isStreaming}
          placeholder={intl.formatMessage({ id: 'nodeChat.placeholder' })}
          size="sm"
          autoFocus
        />
      </form>
    </div>
  )
}
