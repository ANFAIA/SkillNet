import { useMemo, useRef } from 'react'
import { UiSpecRenderer } from '../courses/UiSpecRenderer'
import { gateProgram } from '../courses/kit'
import { ChatMarkdown } from './ChatMarkdown'
import type { ChatMessage } from '../../types'

const CHAT_UI_FORMAT = 'explanation'

export interface ChatAnswerProps {
  message: ChatMessage
}

export function ChatAnswer({ message }: ChatAnswerProps) {
  const gate = useMemo(() => gateProgram(message.program), [message.program])
  const showBlocks = Boolean(message.program) && !gate.blocked && !gate.empty
  const watchedProse = useRef(!message.program)

  // Once we've seen generative content, hold onto it until `program` arrives
  // or we know it won't (connection closed without `ui` event).
  const sawGenerative = useRef(false)
  if (message.generative && message.content) sawGenerative.current = true
  if (message.program) sawGenerative.current = false

  // Validated program arrived — render the final blocks.
  if (showBlocks) {
    return (
      <UiSpecRenderer
        program={message.program ?? null}
        nodeId=""
        format={CHAT_UI_FORMAT}
        arriving={watchedProse.current}
      />
    )
  }

  // Generative mode: streaming or holding the last render while waiting for `ui` event.
  // Uses raw content as the program — UiSpecRenderer handles partial/invalid gracefully.
  if (message.generative && sawGenerative.current && message.content) {
    return (
      <UiSpecRenderer
        program={message.content}
        nodeId=""
        format={CHAT_UI_FORMAT}
        isStreaming={message.isStreaming}
      />
    )
  }

  // Generative mode waiting for first token.
  if (message.generative && message.isStreaming && !message.content) {
    return (
      <span className="typing-dots" aria-label="Generando respuesta">
        <span /><span /><span />
      </span>
    )
  }

  // Two-phase layout in flight (tutor path).
  if (message.isLayingOut) {
    return (
      <span className="typing-dots" aria-label="Preparando formato">
        <span /><span /><span />
      </span>
    )
  }

  // Prose fallback.
  return (
    <>
      <ChatMarkdown content={message.content} isStreaming={message.isStreaming} />
      {message.isStreaming && !message.content && (
        <span className="typing-dots" aria-label="Escribiendo">
          <span /><span /><span />
        </span>
      )}
    </>
  )
}
