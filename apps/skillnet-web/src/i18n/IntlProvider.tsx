import type { ReactNode } from 'react'
import { IntlProvider as ReactIntlProvider } from 'react-intl'
import { messages } from './index'
import { usePreferences } from '../stores/preferences'

export function IntlProvider({ children }: { children: ReactNode }) {
  const locale = usePreferences((s) => s.locale)
  return (
    <ReactIntlProvider locale={locale} messages={messages[locale]} defaultLocale="es">
      {children}
    </ReactIntlProvider>
  )
}
