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
import { ChatAnswer } from '../chat/ChatAnswer'
import { Mascota } from '../mascota'
import { useChat } from '../../api/chat'
import type { ChatContext } from '../../api/chat'
import type { ChatMessage } from '../../types'

export interface NodeChatProps {
  /** Stable ids: the backend reloads title/summary/lesson body from these, org-scoped. */
  nodeId?: string
  courseId?: string
  nodeTitle?: string
  nodeSummary?: string
  /** In-node step progress (0-based) reported by the stepper, for "paso X/N". */
  step?: number
  totalSteps?: number
}

function Bubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[90%] px-3 py-2 text-sm leading-relaxed bg-primary/10 text-text rounded-2xl rounded-br-sm">
          <p className="whitespace-pre-line break-words">{message.content}</p>
        </div>
      </div>
    )
  }

  // Assistant: the same OpenUI-Lang renderer every other SkillNet chat uses. When a
  // `ui` event lands, `ChatAnswer` shows the validated blocks; until then it shows the
  // laying-out dots or the prose fallback. Full width so the blocks use the panel.
  return (
    <div className="flex justify-start">
      <div className="w-full text-sm leading-relaxed text-text">
        <ChatAnswer message={message} />
        {message.citations && message.citations.length > 0 && (
          <div className="mt-2 space-y-0.5">
            {message.citations.map((c, i) => (
              <p key={i} className="text-xs text-text-muted">
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

export function NodeChat({
  nodeId,
  courseId,
  nodeTitle,
  nodeSummary,
  step,
  totalSteps,
}: NodeChatProps) {
  const intl = useIntl()
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const atBottomRef = useRef(true)
  const prevCountRef = useRef(0)

  // Context sent only on the first message — stabilised by useMemo so useChat's
  // dependency does not churn on every render. `node_id`/`course_id` let the backend
  // reload the real node and its on-screen render (org-scoped); the title/summary ride
  // along as a fallback for when no render is pinned yet.
  const context: ChatContext | undefined = useMemo(() => {
    if (!nodeId && !nodeTitle) return undefined
    return {
      ...(nodeId ? { node_id: nodeId } : {}),
      ...(courseId ? { course_id: courseId } : {}),
      ...(nodeTitle ? { nodeTitle } : {}),
      nodeSummary: nodeSummary ?? '',
      ...(typeof step === 'number' ? { step } : {}),
      ...(typeof totalSteps === 'number' ? { totalSteps } : {}),
    }
  }, [nodeId, courseId, nodeTitle, nodeSummary, step, totalSteps])

  // `generative: true` gives the admin-chat render pattern: dots for the whole answer,
  // then reveal the OpenUI blocks at once — no streamed prose that re-renders mid-way.
  const { messages, sendMessage, cancel, isStreaming } = useChat('/chat', context, {
    generative: true,
  })

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
          // El chat vacío ya no es una línea de texto suelta: la mascota saluda con
          // un bocadillo, así que la compañera está presente desde el principio.
          <div className="h-full flex flex-col items-center justify-center px-2">
            <Mascota
              anim="talk"
              say={intl.formatMessage({ id: 'nodeChat.empty' })}
              size={104}
              followCursor
            />
          </div>
        )}
        {messages.map((msg) => (
          <Bubble key={msg.id} message={msg} />
        ))}
      </div>

      {/* Composer */}
      <form onSubmit={(e) => { e.preventDefault(); handleSend() }} className="shrink-0 pt-2">
        <ChatInput
          value={input}
          onChange={setInput}
          onSend={handleSend}
          onStop={cancel}
          isStreaming={isStreaming}
          placeholder={intl.formatMessage({ id: 'nodeChat.placeholder' })}
          size="md"
          autoFocus
        />
      </form>
    </div>
  )
}
