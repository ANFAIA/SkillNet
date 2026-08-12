import { useIntl } from 'react-intl'
import { ClickableSurface } from '../courses/ClickableSurface'
import { ChatAnswer } from './ChatAnswer'
import type { ChatMessage } from '../../types'

export interface ChatBubbleProps {
  message: ChatMessage
}

/** Shared message shell for the employee and admin assistants. */
export function ChatBubble({ message }: ChatBubbleProps) {
  const intl = useIntl()
  const isUser = message.role === 'user'

  const bubble = (
    <div
      className={`${isUser ? 'max-w-[85%] md:max-w-[70%]' : 'w-full'} px-3 py-3 md:px-4 text-sm leading-relaxed ${
        isUser
          ? 'rounded-xl rounded-br-sm bg-primary text-white'
          : 'rounded-xl rounded-bl-sm bg-bg-muted text-text'
      }`}
    >
      {!isUser && message.grounding === 'general' && (
        <p className="mb-1.5 text-xs text-text-muted" data-grounding="general">
          {intl.formatMessage({ id: 'chat.grounding' })}
        </p>
      )}

      {isUser ? (
        <p className="break-words whitespace-pre-line">{message.content}</p>
      ) : (
        <ChatAnswer message={message} />
      )}

      {!isUser && message.citations && message.citations.length > 0 && (
        <details className="mt-2 text-xs text-text-muted">
          <summary className="w-fit cursor-pointer select-none font-medium text-text-secondary">
            {intl.formatMessage({ id: 'chat.sources' }, { count: message.citations.length })}
          </summary>
          <div className="mt-1.5 space-y-1 border-l border-border pl-2.5">
            {message.citations.map((citation, index) => (
              <p key={`${citation.document}-${citation.section ?? ''}-${citation.page ?? ''}-${index}`}>
                {citation.document}
                {citation.section ? ` · ${citation.section}` : ''}
                {citation.page ? ` (p.${citation.page})` : ''}
              </p>
            ))}
          </div>
        </details>
      )}
    </div>
  )

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      {isUser ? (
        bubble
      ) : (
        <ClickableSurface nodeId="" className="min-w-0 max-w-[85%] md:max-w-[70%]">
          {bubble}
        </ClickableSurface>
      )}
    </div>
  )
}
