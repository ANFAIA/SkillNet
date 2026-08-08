import { Outlet, useLocation } from 'react-router-dom'
import { motion, LayoutGroup } from 'framer-motion'
import { AdminSidebar } from './AdminSidebar'
import { Header } from './Header'
import { ErrorBoundary } from '../ErrorBoundary'
import { SidebarProvider, useSidebar } from '../../contexts/SidebarContext'
import { ease, duration } from '../../lib/motion'

const morphSpring = { type: 'spring' as const, stiffness: 200, damping: 28 }

function AdminLayoutInner() {
  const location = useLocation()
  const { collapsed } = useSidebar()
  const isNodeView = /\/nodo\/[^/]+$/.test(location.pathname)

  return (
    <LayoutGroup>
    <div className="flex h-screen overflow-hidden">
      {!isNodeView && <AdminSidebar />}

      <div
        className={`flex-1 flex flex-col min-w-0 transition-[margin-left] duration-300 ease-in-out ${
          isNodeView ? 'ml-0' : collapsed ? 'ml-0 md:ml-16' : 'ml-0 md:ml-[248px]'
        }`}
      >
        {!isNodeView && <Header />}

        <motion.main
          layoutId="admin-main"
          animate={{ borderTopLeftRadius: isNodeView ? 0 : 12 }}
          transition={morphSpring}
          className={`flex-1 bg-bg overflow-x-clip overflow-y-auto flex flex-col ${
            isNodeView ? '' : 'mt-[50px]'
          }`}
        >
          <ErrorBoundary
            fallback={(error, reset) => (
              <div className="p-4 md:p-6">
                <div className="max-w-md mx-auto mt-12 text-center space-y-4">
                  <h2 className="text-lg font-semibold text-text">Algo salio mal</h2>
                  <p className="text-sm text-text-secondary">
                    No se pudo cargar esta pagina. Intenta de nuevo.
                  </p>
                  <pre className="text-xs text-text-muted bg-bg-subtle rounded-lg p-3 overflow-x-auto text-left">
                    {error.message}
                  </pre>
                  <button
                    type="button"
                    onClick={reset}
                    className="px-4 py-2 text-sm font-medium rounded-lg bg-primary text-white hover:opacity-90 transition-opacity"
                  >
                    Reintentar
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
              className={isNodeView ? 'flex-1 min-h-0 flex flex-col' : 'p-4 md:p-6 pb-12 flex-1 min-h-0 flex flex-col'}
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

export function AdminLayout() {
  return (
    <SidebarProvider>
      <AdminLayoutInner />
    </SidebarProvider>
  )
}
