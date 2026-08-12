import { useEffect, useRef, useState } from 'react'
import { useChat } from '../../api/chat'
import { ChatBubble } from './ChatBubble'
import { ChatInput } from './ChatInput'
import { PageHeader } from '../ui/PageHeader'

interface ChatPageProps {
  endpoint: '/chat' | '/chat/admin'
  title: string
  subtitle: string
  emptyTitle: string
  emptySubtitle: string
  placeholder?: string
  generative?: boolean
}

export function ChatPage({
  endpoint,
  title,
  subtitle,
  emptyTitle,
  emptySubtitle,
  placeholder,
  generative = false,
}: ChatPageProps) {
  const { messages, sendMessage, cancel, isStreaming } = useChat(endpoint, undefined, { generative })
  const [input, setInput] = useState('')
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    return cancel
  }, [cancel])
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
    <div className="flex min-h-[calc(100dvh-82px)] flex-col md:min-h-[calc(100dvh-98px)]">
      <div className="mb-4"><PageHeader title={title} description={subtitle} /></div>

      <div className="flex-1 space-y-4 pb-4">
        {messages.length === 0 && (
          <div className="px-4 py-12 text-center">
            <p className="text-sm font-medium text-text">{emptyTitle}</p>
            <p className="mt-1 text-sm text-text-secondary">{emptySubtitle}</p>
          </div>
        )}
        {messages.map((message) => <ChatBubble key={message.id} message={message} />)}
        <div ref={endRef} />
      </div>

      <form onSubmit={(event) => { event.preventDefault(); handleSend() }} className="sticky bottom-0 bg-bg py-4">
        <ChatInput
          value={input}
          onChange={setInput}
          onSend={handleSend}
          onStop={cancel}
          isStreaming={isStreaming}
          placeholder={placeholder}
        />
      </form>
    </div>
  )
}
