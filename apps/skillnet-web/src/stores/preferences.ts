import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type Locale = 'es' | 'en'
export type Theme = 'light' | 'dark' | 'system'

interface PreferencesState {
  locale: Locale
  theme: Theme
  sidebarCollapsed: boolean
  /**
   * When `false` (the default) the mascot reads each node's opening aloud on
   * entry. Clicking the mascot's speaker mutes it, which stops any playback and
   * suppresses the auto-read on later nodes until the learner un-mutes. Reading
   * is on by default; the browser autoplay policy may silence the very first
   * node until any user gesture occurs, and the reading resumes on its own from
   * the next node.
   */
  mascotaMuted: boolean

  setLocale: (locale: Locale) => void
  setTheme: (theme: Theme) => void
  setSidebarCollapsed: (collapsed: boolean) => void
  setMascotaMuted: (muted: boolean) => void
}

export const usePreferences = create<PreferencesState>()(
  persist(
    (set) => ({
      locale: 'es',
      theme: 'system',
      sidebarCollapsed: false,
      mascotaMuted: false,

      setLocale: (locale) => set({ locale }),
      setTheme: (theme) => set({ theme }),
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
      setMascotaMuted: (muted) => set({ mascotaMuted: muted }),
    }),
    { name: 'skillnet-preferences' },
  ),
)
