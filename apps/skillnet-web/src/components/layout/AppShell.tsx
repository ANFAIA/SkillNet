import { LayoutGroup, motion } from 'framer-motion'
import { Outlet, useLocation } from 'react-router-dom'
import { useIntl } from 'react-intl'
import { ErrorBoundary } from '../ErrorBoundary'
import { SidebarProvider, useSidebar } from '../../contexts/SidebarContext'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { duration, ease, spring } from '../../lib/motion'
import { Header } from './Header'
import { Sidebar, type SidebarRole } from './Sidebar'

function AppShellInner({ role }: { role: SidebarRole }) {
  const location = useLocation()
  const intl = useIntl()
  const { collapsed } = useSidebar()
  const reducedMotion = useReducedMotion()
  const isNodeView = /\/nodo\/[^/]+$/.test(location.pathname)

  return (
    <LayoutGroup>
      <div className="flex h-screen overflow-hidden bg-bg">
        {!isNodeView && <Sidebar role={role} />}
        <motion.div
          layout="position"
          transition={reducedMotion ? { duration: 0 } : spring.gentle}
          className={`flex min-w-0 flex-1 flex-col ${isNodeView ? 'ml-0' : collapsed ? 'ml-0 md:ml-16' : 'ml-0 md:ml-[248px]'}`}
        >
          {!isNodeView && <Header />}
          <motion.main
            layoutId="app-main"
            className={`flex-1 bg-bg ${isNodeView ? 'flex flex-col overflow-hidden' : 'mt-[50px] overflow-x-clip overflow-y-auto overscroll-y-contain'}`}
          >
            <ErrorBoundary
              fallback={(error, reset) => (
                <div className="p-4 md:p-6">
                  <div className="mx-auto mt-12 max-w-md space-y-4 text-center">
                    <h2 className="text-lg font-semibold text-text">{intl.formatMessage({ id: 'error.title' })}</h2>
                    <p className="text-sm text-text-secondary">{intl.formatMessage({ id: 'error.description' })}</p>
                    <pre className="overflow-x-auto rounded-lg bg-bg-subtle p-3 text-left text-xs text-text-muted">{error.message}</pre>
                    <button type="button" onClick={reset} className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90">
                      {intl.formatMessage({ id: 'error.retry' })}
                    </button>
                  </div>
                </div>
              )}
            >
              <motion.div
                key={location.pathname}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: duration.normal, ease: ease.base, delay: 0.35 }}
                className={isNodeView ? 'flex min-h-0 flex-1 flex-col' : 'min-h-0 flex-1 p-4 pb-12 md:p-6 md:pb-12'}
              >
                <Outlet />
              </motion.div>
            </ErrorBoundary>
          </motion.main>
        </motion.div>
      </div>
    </LayoutGroup>
  )
}

export function AppShell({ role }: { role: SidebarRole }) {
  return (
    <SidebarProvider>
      <AppShellInner role={role} />
    </SidebarProvider>
  )
}
