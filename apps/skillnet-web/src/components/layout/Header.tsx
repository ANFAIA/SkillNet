import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useIntl } from 'react-intl'
import { motion, AnimatePresence } from 'framer-motion'
import { useMe, useLogout } from '../../api/auth'
import { ThemeToggle } from '../ui/ThemeToggle'
import { useSidebar } from '../../contexts/SidebarContext'
import { transition, duration, ease } from '../../lib/motion'

export function Header() {
  const intl = useIntl()
  const { data: user } = useMe()
  const logout = useLogout()
  const navigate = useNavigate()
  const { collapsed, setMobileOpen } = useSidebar()
  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  /**
   * Permanent entry point for the learner's editable preferences. The initial
   * onboarding stays a short declaration flow; later changes belong to Settings.
   *
   * Gated on the employee role: this header is also the admin one, and an admin has
   * no onboarding wizard.
   */
  const canRerunOnboarding = user?.role === 'employee'

  useEffect(() => {
    if (!open) return
    function onClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  return (
    <header className={`fixed top-0 left-0 right-0 h-[50px] frame-surface border-b border-[var(--frame-border)] flex items-center justify-between md:justify-end px-4 md:px-6 z-10 transition-[left] duration-300 [transition-timing-function:var(--ease-base)] ${collapsed ? 'md:left-16' : 'md:left-[248px]'}`}>
      {/* Mobile menu trigger — opens the sidebar overlay */}
      <motion.button
        type="button"
        onClick={() => setMobileOpen(true)}
        aria-label={intl.formatMessage({ id: 'header.openMenu' })}
        className="md:hidden w-9 h-9 -ml-1 flex items-center justify-center rounded-lg text-white/90 hover:text-white cursor-pointer"
        whileTap={{ scale: 0.9 }}
        transition={transition.micro}
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </motion.button>

      <div className="relative" ref={menuRef}>
        <motion.button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="w-8 h-8 rounded-full border border-white/30 flex items-center justify-center text-white hover:border-white/60 transition-colors cursor-pointer"
          aria-label={intl.formatMessage({ id: 'header.account' })}
          aria-haspopup="menu"
          aria-expanded={open}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.92 }}
          transition={transition.micro}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
        </motion.button>

        <AnimatePresence>
          {open && (
            <motion.div
              role="menu"
              initial={{ opacity: 0, scale: 0.95, y: -6 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: -6 }}
              transition={{ duration: duration.fast, ease: ease.base }}
              className="absolute right-0 top-11 w-56 origin-top-right bg-surface border border-border rounded-xl shadow-lg overflow-hidden"
            >
              {user && (
                <div className="px-4 py-3 border-b border-border">
                  <p className="text-sm font-medium text-text truncate">{user.full_name}</p>
                  <p className="text-xs text-text-muted truncate">{user.email}</p>
                </div>
              )}
              {canRerunOnboarding && (
                <motion.button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setOpen(false)
                    navigate('/empleado/ajustes')
                  }}
                  className="w-full text-left px-4 py-2.5 text-sm text-text hover:bg-bg-muted transition-colors border-b border-border cursor-pointer"
                  whileTap={{ scale: 0.98 }}
                  transition={transition.micro}
                >
                  {intl.formatMessage({ id: 'header.learningPreferences' })}
                </motion.button>
              )}
              <div className="px-4 py-3 border-b border-border">
                <p className="text-xs font-medium text-text-secondary mb-2">
                  {intl.formatMessage({ id: 'settings.theme' })}
                </p>
                <ThemeToggle compact />
              </div>
              <motion.button
                type="button"
                role="menuitem"
                onClick={() => logout.mutate()}
                disabled={logout.isPending}
                className="w-full text-left px-4 py-2.5 text-sm text-text hover:bg-bg-muted transition-colors disabled:opacity-50 cursor-pointer"
                whileTap={{ scale: 0.98 }}
                transition={transition.micro}
              >
                {logout.isPending ? intl.formatMessage({ id: 'header.loggingOut' }) : intl.formatMessage({ id: 'header.logout' })}
              </motion.button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </header>
  )
}
