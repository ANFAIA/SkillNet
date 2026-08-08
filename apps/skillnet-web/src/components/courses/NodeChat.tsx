/**
 * NodeChat — clean chat interface for the NodeView sidebar panel.
 *
 * Uses the learner chat endpoint (`/chat`) with node context on the first
 * message so the tutor knows which lesson the learner is looking at.
 * This is a normal message list + input, NOT the floating spider bubble.
 */

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { useIntl } from 'react-intl'
import { ChatMarkdown } from '../chat/ChatMarkdown'
import { useChat } from '../../api/chat'
import type { ChatContext } from '../../api/chat'
import type { ChatMessage } from '../../types'

export interface NodeChatProps {
  nodeTitle?: string
  nodeSummary?: string
}

const COMPOSER_MAX_HEIGHT = 120

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
  const taRef = useRef<HTMLTextAreaElement>(null)
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

  // Focus input on mount.
  useEffect(() => {
    setTimeout(() => taRef.current?.focus(), 200)
  }, [])

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

  // Auto-grow textarea.
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
    if (!text || isStreaming) return
    void sendMessage(text)
    setInput('')
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
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
      <form onSubmit={handleSubmit} className="shrink-0 flex items-end gap-2 pt-2 border-t border-border">
        <textarea
          ref={taRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          rows={1}
          placeholder={intl.formatMessage({ id: 'nodeChat.placeholder' })}
          disabled={isStreaming}
          className="flex-1 min-h-[36px] max-h-[120px] resize-none rounded-xl bg-bg-subtle px-3 py-2 text-sm text-text outline-none placeholder:text-text-muted disabled:opacity-50"
        />
        {isStreaming ? (
          <button
            type="button"
            onClick={cancel}
            aria-label={intl.formatMessage({ id: 'nodeChat.stop' })}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-bg-muted text-text-muted hover:bg-red-100 hover:text-red-600 transition-colors"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          </button>
        ) : (
          <button
            type="submit"
            disabled={!input.trim()}
            aria-label={intl.formatMessage({ id: 'nodeChat.send' })}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary text-white disabled:opacity-30 transition-colors"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h13" /><path d="M12 5l7 7-7 7" />
            </svg>
          </button>
        )}
      </form>
    </div>
  )
}
