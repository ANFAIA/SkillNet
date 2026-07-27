import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useMe, useLogout } from '../../api/auth'
import { useDynamicCoursesMode } from '../../api/health'
import { useSidebar } from '../../contexts/SidebarContext'
import { transition, duration, ease } from '../../lib/motion'

export function Header() {
  const { data: user } = useMe()
  const logout = useLogout()
  const navigate = useNavigate()
  const { collapsed, setMobileOpen } = useSidebar()
  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  /**
   * The way back into the wizard (§6.1). Skipping writes `experience_level = 'unknown'`
   * and stops the gate from ever firing again, so without an entry point here "lo hago
   * luego" is permanent and the learner profile can never be set.
   *
   * Gated on `'on'` and on the employee role: this header is also the admin one, and
   * below `on` every onboarding route is a 404 — the wizard would bounce straight back.
   */
  const { mode: dynamicMode } = useDynamicCoursesMode()
  const canRerunOnboarding = dynamicMode === 'on' && user?.role === 'employee'

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
    <header className={`fixed top-0 left-0 right-0 h-[50px] frame-surface flex items-center justify-between md:justify-end px-4 md:px-6 z-10 transition-[left] duration-300 ease-in-out ${collapsed ? 'md:left-16' : 'md:left-[248px]'}`}>
      {/* Mobile menu trigger — opens the sidebar overlay */}
      <motion.button
        type="button"
        onClick={() => setMobileOpen(true)}
        aria-label="Abrir menu"
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
          aria-label="Cuenta"
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
              initial={{ opacity: 0, scale: 0.95, y: -6, filter: 'blur(4px)' }}
              animate={{ opacity: 1, scale: 1, y: 0, filter: 'blur(0px)' }}
              exit={{ opacity: 0, scale: 0.96, y: -6, filter: 'blur(4px)' }}
              transition={{ duration: duration.fast, ease: ease.base }}
              className="absolute right-0 top-11 w-56 origin-top-right bg-bg border border-border rounded-xl shadow-lg overflow-hidden"
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
                    navigate('/onboarding')
                  }}
                  className="w-full text-left px-4 py-2.5 text-sm text-text hover:bg-bg-muted transition-colors border-b border-border cursor-pointer"
                  whileTap={{ scale: 0.98 }}
                  transition={transition.micro}
                >
                  Preferencias de aprendizaje
                </motion.button>
              )}
              <motion.button
                type="button"
                role="menuitem"
                onClick={() => logout.mutate()}
                disabled={logout.isPending}
                className="w-full text-left px-4 py-2.5 text-sm text-text hover:bg-bg-muted transition-colors disabled:opacity-50 cursor-pointer"
                whileTap={{ scale: 0.98 }}
                transition={transition.micro}
              >
                {logout.isPending ? 'Cerrando...' : 'Cerrar sesion'}
              </motion.button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </header>
  )
}
