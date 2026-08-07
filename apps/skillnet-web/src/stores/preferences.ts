import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Locale = 'es' | 'en'
export type Theme = 'light' | 'dark' | 'system'

interface PreferencesState {
  locale: Locale
  theme: Theme
  sidebarCollapsed: boolean

  setLocale: (locale: Locale) => void
  setTheme: (theme: Theme) => void
  setSidebarCollapsed: (collapsed: boolean) => void
}

export const usePreferences = create<PreferencesState>()(
  persist(
    (set) => ({
      locale: 'es',
      theme: 'system',
      sidebarCollapsed: false,

      setLocale: (locale) => set({ locale }),
      setTheme: (theme) => set({ theme }),
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
    }),
    { name: 'skillnet-preferences' },
  ),
)
