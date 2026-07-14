import { useSidebar } from '../../contexts/SidebarContext'

interface HeaderProps {
  title: string
}

function HamburgerIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  )
}

export function Header({ title }: HeaderProps) {
  const { collapsed, toggleCollapsed, setMobileOpen } = useSidebar()

  return (
    <header
      className={`fixed top-0 right-0 h-[50px] frame-surface flex items-center justify-between px-4 md:px-6 z-10 transition-[left] duration-300 ease-in-out left-0 ${
        collapsed ? 'md:left-16' : 'md:left-[248px]'
      }`}
    >
      {/* Mobile hamburger */}
      <button
        type="button"
        onClick={() => setMobileOpen(true)}
        className="w-8 h-8 flex items-center justify-center text-white md:hidden"
        aria-label="Abrir menu"
      >
        <HamburgerIcon />
      </button>

      {/* Desktop toggle */}
      <div className="hidden md:flex items-center gap-3 -ml-2">
        <button
          type="button"
          onClick={toggleCollapsed}
          className="w-6 h-6 flex items-center justify-center text-white/40 hover:text-white/80 hover:bg-white/10 rounded transition-all duration-200"
          aria-label={collapsed ? 'Expandir sidebar' : 'Colapsar sidebar'}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={`transition-transform duration-300 ${collapsed ? 'rotate-180' : ''}`}>
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
        <h1 className="text-white text-base font-medium">{title}</h1>
      </div>

      <h1 className="text-white text-base font-medium text-center flex-1 md:hidden">{title}</h1>

      <button
        type="button"
        className="w-8 h-8 rounded-full border border-white/30 flex items-center justify-center text-white hover:border-white/60 transition-colors"
        aria-label="Usuario"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>
      </button>
    </header>
  )
}
