import { Outlet, useLocation } from 'react-router-dom'
import { motion, LayoutGroup } from 'framer-motion'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { ErrorBoundary } from '../ErrorBoundary'
import { SidebarProvider, useSidebar } from '../../contexts/SidebarContext'
import { pageTransition } from '../../lib/motion'

const morphSpring = { type: 'spring' as const, stiffness: 120, damping: 20 }

function AppLayoutInner() {
  const location = useLocation()
  const { collapsed } = useSidebar()

  // NodeView renders as a normal Outlet child — the layout goes fullscreen.
  // A single layoutId on <main> lets framer-motion morph from its current
  // size/position to fullscreen in one coordinated spring, like CreateCourse.
  const isNodeView = /\/nodo\/[^/]+$/.test(location.pathname)

  return (
    <LayoutGroup>
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

        <motion.main
          layoutId="app-main"
          transition={morphSpring}
          style={{ borderTopLeftRadius: isNodeView ? 0 : 12 }}
          className={`flex-1 bg-bg overflow-x-clip overflow-y-auto ${
            isNodeView ? '' : 'mt-[50px]'
          }`}>
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
              Enter-only, and deliberately NOT wrapped in `AnimatePresence`.

              This used to be `<AnimatePresence mode="wait">` with the full
              `{...pageTransition}` (enter + 200 ms accelerating exit). It left the
              main area blank, intermittently, most reliably on /empleado/cursos.

              The cause is that `<Outlet />` is not frozen. Under `mode="wait"` the
              outgoing `motion.div` stays mounted to play its exit — but React keeps
              re-rendering its subtree, and `Outlet` reads the *current* router
              location. So the incoming page mounts *inside the node that is exiting*.
              When that page registers a `layoutId` from in there (`MyCourses` has a
              `LayoutGroup` tab underline, and is the only employee page that does),
              framer's presence bookkeeping never calls `safeToRemove` for the exiting
              key. `AnimatePresence` then never swaps in the incoming child, and the
              node is left sitting at its exit end-state — `opacity: 0`, holding the
              new page's DOM. Right URL, responsive app, nothing visible. Clicking
              again forces a fresh commit, which is why the second try always worked.

              Note this also means the old exit never showed the outgoing page: it was
              fading *the incoming page* out, then snapping it back to opacity 0 and
              fading it in again. So the 200 ms it cost bought a defect, not polish.

              Without `AnimatePresence` there is no exit phase, no presence
              bookkeeping and no `safeToRemove` — React swaps the keyed children in a
              single commit, and the new page runs its fade-in. Nothing can fail to
              complete because nothing has to report completion. Navigation also lands
              200 ms sooner (~300 ms total instead of 500 ms).

              `pageTransition.exit` is still correct for an `AnimatePresence` whose
              children are stable (see MotionDemo) — it is the unfrozen `Outlet` that
              makes it unsafe here.
            */}
            <motion.div
              key={location.pathname}
              initial={pageTransition.initial}
              animate={pageTransition.animate}
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
