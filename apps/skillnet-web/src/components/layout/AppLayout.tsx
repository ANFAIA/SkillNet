import { Outlet, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { ErrorBoundary } from '../ErrorBoundary'
import { SidebarProvider, useSidebar } from '../../contexts/SidebarContext'
import { pageTransition } from '../../lib/motion'

function AppLayoutInner() {
  const location = useLocation()
  const { collapsed } = useSidebar()

  return (
    <div className="flex min-h-screen overflow-x-hidden">
      <Sidebar />

      <div
        className={`flex-1 flex flex-col min-w-0 transition-[margin-left] duration-300 ease-in-out ml-0 ${
          collapsed ? 'md:ml-16' : 'md:ml-[248px]'
        }`}
      >
        <Header />

        <main className="flex-1 mt-[50px] bg-bg md:rounded-tl-xl overflow-y-auto overflow-x-hidden">
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
            <AnimatePresence mode="wait">
              <motion.div
                key={location.pathname}
                {...pageTransition}
                className="p-4 md:p-6"
              >
                <Outlet />
              </motion.div>
            </AnimatePresence>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  )
}

export function AppLayout() {
  return (
    <SidebarProvider>
      <AppLayoutInner />
    </SidebarProvider>
  )
}
