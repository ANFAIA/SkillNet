import { useMemo } from 'react'
import { UiSpecRenderer } from '../courses/UiSpecRenderer'
import { ClickableSurface } from '../courses/ClickableSurface'
import { gateProgram } from '../courses/kit'
import { ChatMarkdown } from './ChatMarkdown'
import type { ChatMessage } from '../../types'

const CHAT_UI_FORMAT = 'explanation'

export interface ChatAnswerProps {
  message: ChatMessage
}

/**
 * Curio pattern: generative replies show dots for the ENTIRE streaming phase,
 * then reveal the complete panel at once when done. No progressive component
 * rendering — partial OpenUI Lang parses out of order and reads as janky.
 */
export function ChatAnswer({ message }: ChatAnswerProps) {
  const gate = useMemo(() => gateProgram(message.program), [message.program])
  const showBlocks = Boolean(message.program) && !gate.blocked && !gate.empty

  // Validated program arrived — render the blocks. Wrapped in ClickableSurface so
  // words are clickable and "Ver mas" opens the ExplainModal.
  if (showBlocks) {
    return (
      <ClickableSurface nodeId={null}>
        <UiSpecRenderer
          program={message.program ?? null}
          nodeId=""
          format={CHAT_UI_FORMAT}
          arriving
        />
      </ClickableSurface>
    )
  }

  // Generative mode: dots for the WHOLE generation. Content is OpenUI Lang code
  // that must not be shown raw. Dots stay until `program` arrives via `ui` event.
  if (message.generative && (message.isStreaming || !message.program)) {
    // Streaming done but no program yet — still waiting for `ui` event, or
    // validation failed. If content looks like code, keep dots. If it's clearly
    // not code (validation failed, model wrote prose), show it as markdown.
    if (!message.isStreaming && message.content && !/^\s*root\s*=/.test(message.content)) {
      // Same surface as the prose branch below, for the same reason: `ChatMarkdown`
      // paints every word as an `.entity` with `cursor: pointer`, so rendering it bare
      // makes the answer *look* click-to-explain and do nothing. This branch is the
      // admin assistant's normal outcome — the model wrote prose instead of a program —
      // and `Chat.tsx` does not wrap the bubble, so nothing else supplies the handler.
      return (
        <ClickableSurface nodeId={null}>
          <ChatMarkdown content={message.content} isStreaming={false} />
        </ClickableSurface>
      )
    }

    return (
      <span className="typing-dots" role="status" aria-label="Generando respuesta">
        <span /><span /><span />
      </span>
    )
  }

  // Two-phase layout in flight (tutor path).
  if (message.isLayingOut) {
    return (
      <span className="typing-dots" role="status" aria-label="Preparando formato">
        <span /><span /><span />
      </span>
    )
  }

  // Prose fallback, streaming or not — one branch, always inside a ClickableSurface.
  //
  // The streaming half used to render bare, on the grounds that "re-measuring the
  // surface on every token would thrash layout". The surface measures nothing: it
  // attaches two handlers, and the only thing that measures is the phrase band, which
  // does so only once a selection exists. Meanwhile `ChatMarkdown` paints every word as
  // an `.entity` with `cursor: pointer`, so leaving the handler off made a half-written
  // answer *look* click-to-explain and do nothing.
  return (
    <ClickableSurface nodeId={null}>
      <ChatMarkdown content={message.content} isStreaming={message.isStreaming} />
      {message.isStreaming && !message.content && (
        <span className="typing-dots" role="status" aria-label="Escribiendo">
          <span /><span /><span />
        </span>
      )}
    </ClickableSurface>
  )
}
