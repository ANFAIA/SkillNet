import { Outlet, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import { AdminSidebar } from './AdminSidebar'
import { Header } from './Header'
import { ErrorBoundary } from '../ErrorBoundary'
import { SidebarProvider, useSidebar } from '../../contexts/SidebarContext'
import { pageTransition } from '../../lib/motion'

function AdminLayoutInner() {
  const location = useLocation()
  const { collapsed } = useSidebar()

  return (
    <div className="flex min-h-screen overflow-x-hidden">
      <AdminSidebar />

      <div
        className={`flex-1 flex flex-col min-w-0 transition-[margin-left] duration-300 ease-in-out ml-0 ${
          collapsed ? 'md:ml-16' : 'md:ml-[248px]'
        }`}
      >
        <Header />

        {/* No `overflow-y-auto` — see the note in AppLayout. This grows with its content
            and the page scrolls; the sidebar and header are both `fixed`, so nothing here
            needed a scroll box of its own. */}
        <main className="flex-1 mt-[50px] bg-bg md:rounded-tl-xl overflow-x-hidden">
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
            {/*
              Enter-only, no `AnimatePresence`. Same fix, same reason as
              `AppLayout` — see the long comment there. This layout had the identical
              `AnimatePresence mode="wait"` + unfrozen `<Outlet />` shape, so it had
              the identical blank-main bug latent in it: any admin page that mounts a
              `layoutId` would strand the exiting node at `opacity: 0`.
            */}
            <motion.div
              key={location.pathname}
              initial={pageTransition.initial}
              animate={pageTransition.animate}
              className="p-4 md:p-6"
            >
              <Outlet />
            </motion.div>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  )
}

export function AdminLayout() {
  return (
    <SidebarProvider>
      <AdminLayoutInner />
    </SidebarProvider>
  )
}
