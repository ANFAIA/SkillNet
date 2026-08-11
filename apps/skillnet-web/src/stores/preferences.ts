import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Locale = 'es' | 'en'
export type Theme = 'light' | 'dark' | 'system'

interface PreferencesState {
  locale: Locale
  theme: Theme
  sidebarCollapsed: boolean
  /**
   * When on, the mascot reads each node's opening aloud on entry. Off by default:
   * audio is opt-in and only starts after a user gesture (browsers block autoplay,
   * and it is intrusive). Enabling it is itself a gesture, which is what lets the
   * following nodes read without a fresh click.
   */
  readAloud: boolean

  setLocale: (locale: Locale) => void
  setTheme: (theme: Theme) => void
  setSidebarCollapsed: (collapsed: boolean) => void
  setReadAloud: (on: boolean) => void
}

export const usePreferences = create<PreferencesState>()(
  persist(
    (set) => ({
      locale: 'es',
      theme: 'system',
      sidebarCollapsed: false,
      readAloud: false,

      setLocale: (locale) => set({ locale }),
      setTheme: (theme) => set({ theme }),
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
      setReadAloud: (on) => set({ readAloud: on }),
    }),
    { name: 'skillnet-preferences' },
  ),
)
