import { Outlet, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { AdminSidebar } from './AdminSidebar'
import { Header } from './Header'

const pageTitles: Record<string, string> = {
  '/admin': 'Panel de Empresa',
  '/admin/empleados': 'Empleados',
  '/admin/contenido': 'Contenido',
  '/admin/crear-curso': 'Crear Curso',
}

function getTitle(pathname: string): string {
  return pageTitles[pathname] ?? 'Admin'
}

export function AdminLayout() {
  const location = useLocation()
  const title = getTitle(location.pathname)

  return (
    <div className="flex min-h-screen bg-primary">
      <AdminSidebar />

      <div className="flex-1 ml-[248px] flex flex-col">
        <Header title={title} />

        <main className="flex-1 mt-[50px] bg-bg rounded-tl-xl overflow-y-auto">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="p-6"
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
    </div>
  )
}
