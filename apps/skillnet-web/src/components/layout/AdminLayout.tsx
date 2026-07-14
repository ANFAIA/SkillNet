import { Outlet, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { AdminSidebar } from './AdminSidebar'
import { Header } from './Header'
import { SidebarProvider, useSidebar } from '../../contexts/SidebarContext'

const pageTitles: Record<string, string> = {
  '/admin': 'Panel de Empresa',
  '/admin/empleados': 'Empleados',
  '/admin/contenido': 'Contenido',
  '/admin/crear-curso': 'Crear Curso',
}

function getTitle(pathname: string): string {
  return pageTitles[pathname] ?? 'Admin'
}

function AdminLayoutInner() {
  const location = useLocation()
  const title = getTitle(location.pathname)
  const { collapsed } = useSidebar()

  return (
    <div className="flex min-h-screen bg-primary overflow-x-hidden">
      <AdminSidebar />

      <div
        className={`flex-1 flex flex-col min-w-0 transition-[margin-left] duration-300 ease-in-out ml-0 md:ml-16 ${
          !collapsed ? 'lg:ml-[248px]' : ''
        }`}
      >
        <Header title={title} />

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

export function AdminLayout() {
  return (
    <SidebarProvider>
      <AdminLayoutInner />
    </SidebarProvider>
  )
}
