import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// Provide a default IntlProvider context for all tests.  Components that
// call `useIntl()` (directly or via `<FormattedMessage>`) will get the
// Spanish messages instead of throwing the "missing IntlProvider" error.
vi.mock('react-intl', async () => {
  const actual = await vi.importActual<typeof import('react-intl')>('react-intl')
  const { es } = await import('../i18n/es')
  const intl = actual.createIntl({ locale: 'es', messages: es, defaultLocale: 'es' })
  return {
    ...actual,
    useIntl: () => intl,
  }
})

afterEach(() => {
  cleanup()
})
