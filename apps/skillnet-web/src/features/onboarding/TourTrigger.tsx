import { useNavigate, useLocation } from 'react-router-dom'
import { useIntl } from 'react-intl'
import { motion } from 'framer-motion'
import { transition } from '../../lib/motion'
import { useTourStore } from './useTourStore'

const HOME_PATH = '/empleado'

/**
 * The persistent, unobtrusive "?" that reopens the tour (docs/design/onboarding.md
 * §2.4 — "reabrible desde un '?' persistente"). Lives in the employee header next to
 * the account button. The tour's anchors are on the home, so if the learner is
 * elsewhere we route home first, then start once the dashboard has mounted.
 */
export function TourTrigger() {
  const intl = useIntl()
  const navigate = useNavigate()
  const location = useLocation()
  const start = useTourStore((s) => s.start)

  function handleClick() {
    if (location.pathname !== HOME_PATH) {
      navigate(HOME_PATH)
      // Let the route + dashboard cards mount before the spotlight looks for them.
      window.setTimeout(() => start(), 450)
      return
    }
    start()
  }

  return (
    <motion.button
      type="button"
      onClick={handleClick}
      aria-label={intl.formatMessage({ id: 'onboarding.tour.reopen' })}
      title={intl.formatMessage({ id: 'onboarding.tour.reopen' })}
      className="flex h-8 w-8 items-center justify-center rounded-full border border-border text-text-muted transition-colors hover:border-border-strong hover:text-text cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.92 }}
      transition={transition.micro}
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="10" />
        <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
    </motion.button>
  )
}
