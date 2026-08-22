import { useIntl } from 'react-intl'
import { ChatPage } from '../../components/chat/ChatPage'

export function Chat() {
  const intl = useIntl()

  return (
    <ChatPage
      endpoint="/chat"
      title={intl.formatMessage({ id: 'empChat.title' })}
      subtitle={intl.formatMessage({ id: 'empChat.subtitle' })}
      emptyTitle={intl.formatMessage({ id: 'empChat.emptyTitle' })}
      emptySubtitle={intl.formatMessage({ id: 'empChat.emptySubtitle' })}
      generative
    />
  )
}
