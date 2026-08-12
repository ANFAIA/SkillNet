import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import {
  DEFAULT_ACCENT_COLOR,
  DEFAULT_CUSTOM_ACCENT,
  type AccentColor,
} from '../lib/accent-themes'
import { DEFAULT_UI_PRESET, type UiPreset } from '../lib/ui-presets'

export type Locale = 'es' | 'en'
export type Theme = 'light' | 'dark' | 'system'

interface PreferencesState {
  locale: Locale
  theme: Theme
  accentColor: AccentColor
  customAccent: string
  uiPreset: UiPreset
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
  setAccentColor: (accentColor: AccentColor) => void
  setCustomAccent: (customAccent: string) => void
  setUiPreset: (uiPreset: UiPreset) => void
  setSidebarCollapsed: (collapsed: boolean) => void
  setMascotaMuted: (muted: boolean) => void
}

export const usePreferences = create<PreferencesState>()(
  persist(
    (set) => ({
      locale: 'es',
      theme: 'system',
      accentColor: DEFAULT_ACCENT_COLOR,
      customAccent: DEFAULT_CUSTOM_ACCENT,
      uiPreset: DEFAULT_UI_PRESET,
      sidebarCollapsed: false,
      mascotaMuted: false,

      setLocale: (locale) => set({ locale }),
      setTheme: (theme) => set({ theme }),
      setAccentColor: (accentColor) => set({ accentColor }),
      setCustomAccent: (customAccent) => set({ customAccent, accentColor: 'custom' }),
      setUiPreset: (uiPreset) => set({ uiPreset }),
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
      setMascotaMuted: (muted) => set({ mascotaMuted: muted }),
    }),
    { name: 'skillnet-preferences' },
  ),
)
