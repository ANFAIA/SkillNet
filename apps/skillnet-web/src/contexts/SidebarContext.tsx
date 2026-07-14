import { createContext, useContext, useState, useEffect, useCallback } from 'react'

interface SidebarContextValue {
  collapsed: boolean
  mobileOpen: boolean
  toggleCollapsed: () => void
  setMobileOpen: (open: boolean) => void
  closeMobile: () => void
}

const SidebarContext = createContext<SidebarContextValue | null>(null)

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia(query).matches : false,
  )

  useEffect(() => {
    const mql = window.matchMedia(query)
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches)
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [query])

  return matches
}

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const isMobile = useMediaQuery('(max-width: 767px)')
  const isTablet = useMediaQuery('(min-width: 768px) and (max-width: 1024px)')

  // On tablet, start collapsed; on desktop, start expanded
  const [collapsed, setCollapsed] = useState(isTablet)
  const [mobileOpen, setMobileOpen] = useState(false)

  // Sync collapsed state when breakpoint changes
  useEffect(() => {
    if (isMobile) {
      setCollapsed(false) // irrelevant on mobile (overlay mode)
      setMobileOpen(false)
    } else if (isTablet) {
      setCollapsed(true)
      setMobileOpen(false)
    } else {
      setCollapsed(false)
      setMobileOpen(false)
    }
  }, [isMobile, isTablet])

  const toggleCollapsed = useCallback(() => {
    setCollapsed((prev) => !prev)
  }, [])

  const closeMobile = useCallback(() => {
    setMobileOpen(false)
  }, [])

  return (
    <SidebarContext.Provider
      value={{ collapsed, mobileOpen, toggleCollapsed, setMobileOpen, closeMobile }}
    >
      {children}
    </SidebarContext.Provider>
  )
}

export function useSidebar(): SidebarContextValue {
  const ctx = useContext(SidebarContext)
  if (!ctx) throw new Error('useSidebar must be used within SidebarProvider')
  return ctx
}
