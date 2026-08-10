/**
 * NodeChat — clean chat interface for the NodeView sidebar panel.
 *
 * Uses the learner chat endpoint (`/chat`) with node context on the first
 * message so the tutor knows which lesson the learner is looking at.
 * This is a normal message list + input, NOT the floating spider bubble.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useIntl } from 'react-intl'
import { ChatInput } from '../chat/ChatInput'
import { ChatAnswer } from '../chat/ChatAnswer'
import { Mascota } from '../mascota'
import { useChat } from '../../api/chat'
import type { ChatContext } from '../../api/chat'
import type { ChatMessage } from '../../types'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { duration, ease } from '../../lib/motion'

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
  const intl = useIntl()
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
        {/* Same provenance note the admin chat shows: when nothing in the company's
            material covered the question the tutor answered from general knowledge,
            and the label keeps that honest (see ChatGrounding). */}
        {message.grounding === 'general' && (
          <p className="text-xs text-text-muted mb-1.5" data-grounding="general">
            {intl.formatMessage({ id: 'chat.grounding' })}
          </p>
        )}
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
  const reduceMotion = useReducedMotion()
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
      {/* Messages. `relative` so the greeting can leave as an absolute overlay while
          the conversation fades in underneath it — a Curio-style hand-off, not a cut. */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="relative flex-1 overflow-y-auto min-h-0 pb-2"
        style={{ scrollbarWidth: 'thin' }}
      >
        {/* The empty state does not just vanish when the first message lands: it fades
            and drifts up (opacity + translate + scale, no blur) while the conversation
            fades in, so the mascota's greeting reads as handing off to the chat.
            Under reduced motion it is a plain opacity swap — no transform. */}
        <AnimatePresence initial={false}>
          {messages.length === 0 && (
            <motion.div
              key="empty"
              // La mascota saluda: la compañera está presente desde el principio.
              className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-4 text-center"
              exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -12, scale: 0.96 }}
              transition={{
                duration: reduceMotion ? duration.fast : duration.normal,
                ease: ease.base,
              }}
            >
              <Mascota anim="saludar" size={88} followCursor />
              <p className="text-sm text-text-secondary max-w-[15rem]">
                {intl.formatMessage({ id: 'nodeChat.empty' })}
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        {messages.length > 0 && (
          <motion.div
            className="space-y-3"
            initial={reduceMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{
              duration: duration.normal,
              ease: ease.base,
              // A beat behind the greeting's exit so it reads as a hand-off, not a crossfade.
              delay: reduceMotion ? 0 : duration.fast,
            }}
          >
            {messages.map((msg) => (
              <Bubble key={msg.id} message={msg} />
            ))}
          </motion.div>
        )}
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
