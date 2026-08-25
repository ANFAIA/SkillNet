import '@testing-library/jest-dom/vitest'
import { cleanup, configure } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// Testing Library's async helpers (`findBy*`, `waitFor`) carry their OWN timeout, and it
// defaults to 1000 ms no matter what `testTimeout` says — so the 15 s in vite.config.ts
// never applied to them. That 1 s is what the "passes alone, fails in the full suite"
// failures were actually hitting: under full-suite CPU load a jsdom + framer-motion mount
// slips past a second, and the helper gives up long before the test does. 5 s absorbs the
// load jitter and still sits well under `testTimeout`, so a genuinely missing element
// still fails the test — just five seconds later instead of one.
configure({ asyncUtilTimeout: 5000 })

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
