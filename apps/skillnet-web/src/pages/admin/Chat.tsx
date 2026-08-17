import { useIntl } from 'react-intl'
import { ChatPage } from '../../components/chat/ChatPage'

export function AdminChat() {
  const intl = useIntl()

  return (
    <ChatPage
      endpoint="/chat/admin"
      title={intl.formatMessage({ id: 'chat.title' })}
      emptyTitle={intl.formatMessage({ id: 'chat.emptyTitle' })}
      emptySubtitle={intl.formatMessage({ id: 'chat.emptySubtitle' })}
      placeholder={intl.formatMessage({ id: 'chat.placeholder' })}
    />
  )
}
