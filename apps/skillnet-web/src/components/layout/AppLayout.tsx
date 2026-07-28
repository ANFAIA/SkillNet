import { Outlet, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
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

        {/* No `overflow-y-auto`: this element grows with its content and the *page*
            scrolls. It used to be a scroll box, which put a second scrollbar inside the
            layout — most obvious on Empleados, where a long list scrolled inside a panel
            while the window stayed still. Nothing needed it: the sidebar is
            `fixed left-0 top-0 bottom-0` and the header is `fixed top-0`, so both stay
            put under page scroll on their own. `overflow-x-clip` and not `hidden`: per spec,
            `overflow-x: hidden` forces the other axis from `visible` to `auto`, which
            would quietly recreate the scroll container we just removed. `clip` does
            not, and still stops a wide child blowing out the layout sideways. */}
        <main className="flex-1 mt-[50px] bg-bg md:rounded-tl-xl overflow-x-clip">
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
              blurring *the incoming page* out, then snapping it back to blur(6px) and
              fading it in again. So the 200 ms it cost bought a defect, not polish.

              Without `AnimatePresence` there is no exit phase, no presence
              bookkeeping and no `safeToRemove` — React swaps the keyed children in a
              single commit, and the new page runs its blur-in. Nothing can fail to
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

export function AppLayout() {
  return (
    <SidebarProvider>
      <AppLayoutInner />
    </SidebarProvider>
  )
}
