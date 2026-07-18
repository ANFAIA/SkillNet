import { useEffect, useRef, useState } from 'react'
import { useMe, useLogout } from '../../api/auth'

export function Header() {
  const { data: user } = useMe()
  const logout = useLogout()
  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function onClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  return (
    <header className="fixed top-0 right-0 h-[50px] frame-surface flex items-center justify-end px-4 md:px-6 z-10">
      <div className="relative" ref={menuRef}>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="w-8 h-8 rounded-full border border-white/30 flex items-center justify-center text-white hover:border-white/60 transition-colors"
          aria-label="Cuenta"
          aria-haspopup="menu"
          aria-expanded={open}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
        </button>

        {open && (
          <div
            role="menu"
            className="absolute right-0 top-11 w-56 bg-bg border border-border rounded-lg shadow-lg overflow-hidden"
          >
            {user && (
              <div className="px-4 py-3 border-b border-border">
                <p className="text-sm font-medium text-text truncate">{user.full_name}</p>
                <p className="text-xs text-text-muted truncate">{user.email}</p>
              </div>
            )}
            <button
              type="button"
              role="menuitem"
              onClick={() => logout.mutate()}
              disabled={logout.isPending}
              className="w-full text-left px-4 py-2.5 text-sm text-text hover:bg-bg-muted transition-colors disabled:opacity-50 cursor-pointer"
            >
              {logout.isPending ? 'Cerrando...' : 'Cerrar sesion'}
            </button>
          </div>
        )}
      </div>
    </header>
  )
}
