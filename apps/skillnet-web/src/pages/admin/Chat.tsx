import { useState } from 'react'
import { Button } from '../../components/ui'

interface ChatMessage {
  id: string
  sender: 'user' | 'bot'
  text: string
}

const initialMessages: ChatMessage[] = [
  {
    id: 'a1',
    sender: 'bot',
    text: 'Hola. Soy el asistente de administracion de SkillNet. Puedo ayudarte con la gestion de cursos, empleados, habilidades y la plataforma en general. ¿En que puedo ayudarte?',
  },
]

function SendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}

export function AdminChat() {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages)
  const [input, setInput] = useState('')

  function handleSend() {
    const text = input.trim()
    if (!text) return

    const userMessage: ChatMessage = {
      id: `msg-${Date.now()}`,
      sender: 'user',
      text,
    }

    const botMessage: ChatMessage = {
      id: `msg-${Date.now()}-bot`,
      sender: 'bot',
      text: 'Estoy procesando tu consulta. Esta funcionalidad estara disponible proximamente con conexion al sistema de IA.',
    }

    setMessages((prev) => [...prev, userMessage, botMessage])
    setInput('')
  }

  return (
    <div className="flex flex-col h-[calc(100vh-50px-48px)]">
      <div className="mb-4">
        <h2 className="text-xl font-semibold text-text">Asistente</h2>
        <p className="text-sm text-text-secondary mt-0.5">Pregunta sobre cursos, empleados o la plataforma</p>
      </div>

      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[70%] px-4 py-3 text-sm leading-relaxed ${
                msg.sender === 'user'
                  ? 'bg-primary text-white rounded-xl rounded-br-sm'
                  : 'bg-bg-muted text-text rounded-xl rounded-bl-sm'
              }`}
            >
              <p className="whitespace-pre-line">{msg.text}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="flex gap-2 pt-4 border-t border-border">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              handleSend()
            }
          }}
          placeholder="Escribe tu consulta..."
          className="flex-1 px-3 py-2 text-sm text-text border border-border rounded-lg bg-bg placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors"
        />
        <Button size="md" onClick={handleSend} disabled={!input.trim()}>
          <SendIcon />
        </Button>
      </div>
    </div>
  )
}
