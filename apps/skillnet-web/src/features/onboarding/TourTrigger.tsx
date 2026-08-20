import { useNavigate, useLocation } from 'react-router-dom'
import { useIntl } from 'react-intl'
import { motion } from 'framer-motion'
import { transition } from '../../lib/motion'
import { useTourStore } from './useTourStore'
import type { SidebarRole } from '../../components/layout/Sidebar'

const HOME_PATH: Record<SidebarRole, string> = {
  employee: '/empleado',
  admin: '/admin',
}

/**
 * The persistent, unobtrusive "?" that reopens the tour (docs/design/onboarding.md
 * §2.4 — "reabrible desde un '?' persistente"). Lives in the header next to the
 * account button, for both roles. The tour's anchors are on the role's home, so if
 * the user is elsewhere we route home first, then start once it has mounted.
 */
export function TourTrigger({ role = 'employee' }: { role?: SidebarRole }) {
  const intl = useIntl()
  const navigate = useNavigate()
  const location = useLocation()
  const start = useTourStore((s) => s.start)
  const homePath = HOME_PATH[role]

  function handleClick() {
    if (location.pathname !== homePath) {
      navigate(homePath)
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
