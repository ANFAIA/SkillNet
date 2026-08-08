import { Outlet, useLocation } from 'react-router-dom'
import { motion, LayoutGroup } from 'framer-motion'
import { useIntl } from 'react-intl'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { ErrorBoundary } from '../ErrorBoundary'
import { SidebarProvider, useSidebar } from '../../contexts/SidebarContext'
import { ease, duration } from '../../lib/motion'

const morphSpring = { type: 'spring' as const, stiffness: 200, damping: 28 }

function AppLayoutInner() {
  const location = useLocation()
  const intl = useIntl()
  const { collapsed } = useSidebar()

  // NodeView renders as a normal Outlet child — the layout goes fullscreen.
  // A single layoutId on <main> lets framer-motion morph from its current
  // size/position to fullscreen in one coordinated spring, like CreateCourse.
  const isNodeView = /\/nodo\/[^/]+$/.test(location.pathname)

  return (
    <LayoutGroup>
    <div className="flex h-screen overflow-hidden">
      {!isNodeView && <Sidebar />}

      <div
        className={`flex-1 flex flex-col min-w-0 transition-[margin-left] duration-300 ease-in-out ${
          isNodeView ? 'ml-0' : collapsed ? 'ml-0 md:ml-16' : 'ml-0 md:ml-[248px]'
        }`}
      >
        {!isNodeView && <Header />}

        <motion.main
          layoutId="app-main"
          animate={{ borderTopLeftRadius: isNodeView ? 0 : 12 }}
          transition={morphSpring}
          className={`flex-1 bg-bg overflow-x-clip overflow-y-auto ${
            isNodeView ? '' : 'mt-[50px]'
          }`}
        >
          <ErrorBoundary
            fallback={(error, reset) => (
              <div className="p-4 md:p-6">
                <div className="max-w-md mx-auto mt-12 text-center space-y-4">
                  <h2 className="text-lg font-semibold text-text">{intl.formatMessage({ id: 'error.title' })}</h2>
                  <p className="text-sm text-text-secondary">
                    {intl.formatMessage({ id: 'error.description' })}
                  </p>
                  <pre className="text-xs text-text-muted bg-bg-subtle rounded-lg p-3 overflow-x-auto text-left">
                    {error.message}
                  </pre>
                  <button
                    type="button"
                    onClick={reset}
                    className="px-4 py-2 text-sm font-medium rounded-lg bg-primary text-white hover:opacity-90 transition-opacity"
                  >
                    {intl.formatMessage({ id: 'error.retry' })}
                  </button>
                </div>
              </div>
            )}
          >
            {/* Content reveal: opacity 0 → 1 with a 0.35s delay so the layout morph
                spring settles before content appears. Same pattern as CreateCourse. */}
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: duration.normal, ease: ease.base, delay: 0.35 }}
              className={isNodeView ? 'flex-1 min-h-0 flex flex-col' : 'p-4 md:p-6 pb-12'}
            >
              <Outlet />
            </motion.div>
          </ErrorBoundary>
        </motion.main>
      </div>
    </div>
    </LayoutGroup>
  )
}

export function AppLayout() {
  return (
    <SidebarProvider>
      <AppLayoutInner />
    </SidebarProvider>
  )
}
