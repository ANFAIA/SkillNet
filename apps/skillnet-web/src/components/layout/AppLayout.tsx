import { Outlet, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Sidebar } from './Sidebar'
import { Header } from './Header'

const pageTitles: Record<string, string> = {
  '/empleado': 'Inicio',
  '/empleado/cursos': 'Mis Cursos',
  '/empleado/skillmap': 'Skill Map',
  '/empleado/chat': 'Chat',
}

function getTitle(pathname: string): string {
  if (pathname.startsWith('/empleado/curso/')) return 'Curso'
  return pageTitles[pathname] ?? 'SkillNet'
}

export function AppLayout() {
  const location = useLocation()
  const title = getTitle(location.pathname)

  return (
    <div className="flex min-h-screen bg-primary">
      <Sidebar />

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
