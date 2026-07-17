import { Outlet, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { SidebarProvider, useSidebar } from '../../contexts/SidebarContext'

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
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="p-4 md:p-6"
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
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
