import { NavLink } from 'react-router-dom'

interface NavItem {
  label: string
  to: string
  icon: React.ReactNode
}

const navItems: NavItem[] = [
  {
    label: 'Inicio',
    to: '/empleado',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
        <polyline points="9 22 9 12 15 12 15 22" />
      </svg>
    ),
  },
  {
    label: 'Mis Cursos',
    to: '/empleado/cursos',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
      </svg>
    ),
  },
  {
    label: 'Skill Map',
    to: '/empleado/skillmap',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
      </svg>
    ),
  },
  {
    label: 'Chat',
    to: '/empleado/chat',
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    ),
  },
]

export function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 bottom-0 w-[248px] frame-surface flex flex-col z-20">
      {/* Logo */}
      <div className="flex flex-col items-center py-5 gap-2">
        <div className="w-12 h-12 bg-white rounded-xl flex items-center justify-center p-1">
          <img src="/logo.png" alt="SkillNet" className="w-full h-full object-contain" />
        </div>
        <span className="text-white text-sm font-semibold">SkillNet</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 mt-6 flex flex-col gap-1">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/empleado'}
            className={({ isActive }) =>
              `flex items-center gap-3 h-10 text-sm font-medium transition-colors ml-10 pl-4 pr-4 ${
                isActive
                  ? 'bg-white text-primary rounded-l-xl'
                  : 'text-white/80 hover:text-white'
              }`
            }
          >
            {item.icon}
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
