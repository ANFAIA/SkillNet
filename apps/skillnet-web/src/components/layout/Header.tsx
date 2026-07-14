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
  const { collapsed, setMobileOpen } = useSidebar()

  return (
    <header
      className={`fixed top-0 right-0 h-[50px] frame-surface flex items-center justify-between px-4 md:px-6 z-10 transition-[left] duration-300 ease-in-out left-0 md:left-16 ${
        !collapsed ? 'lg:left-[248px]' : ''
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

      <h1 className="text-white text-base font-medium md:text-left text-center flex-1 md:flex-none">{title}</h1>

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
