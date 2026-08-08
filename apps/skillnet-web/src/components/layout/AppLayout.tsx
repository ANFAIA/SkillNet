import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { ErrorBoundary } from '../ErrorBoundary'
import { SidebarProvider, useSidebar } from '../../contexts/SidebarContext'

function AppLayoutInner() {
  const location = useLocation()
  const { collapsed } = useSidebar()

  // NodeView renders as a normal Outlet child — the layout goes fullscreen.
  // View Transitions API handles the crossfade between routes; no layoutId needed.
  const isNodeView = /\/nodo\/[^/]+$/.test(location.pathname)

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar — hidden when NodeView is active (no animation, just gone) */}
      {!isNodeView && <Sidebar />}

      <div
        className={`flex-1 flex flex-col min-w-0 transition-[margin-left] duration-300 ease-in-out ${
          isNodeView ? 'ml-0' : collapsed ? 'ml-0 md:ml-16' : 'ml-0 md:ml-[248px]'
        }`}
      >
        {/* Header — hidden when NodeView is active */}
        {!isNodeView && <Header />}

        <main
          className={`flex-1 bg-bg overflow-x-clip overflow-y-auto ${
            isNodeView ? '' : 'mt-[50px]'
          }`}
          style={{ borderTopLeftRadius: isNodeView ? 0 : 12 }}
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
            <div className={isNodeView ? 'flex-1 min-h-0 flex flex-col' : 'p-4 md:p-6 pb-12'}>
              <Outlet />
            </div>
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
