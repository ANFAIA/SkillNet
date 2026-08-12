import { ChatPage } from '../../components/chat/ChatPage'

export function Chat() {
  return (
    <ChatPage
      endpoint="/chat"
      title="Chat"
      subtitle="Pregunta sobre tus cursos y procedimientos"
      emptyTitle="Hazme una pregunta"
      emptySubtitle="Puedo ayudarte con cualquier tema de tus cursos y procedimientos."
      generative
    />
  )
}
