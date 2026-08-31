import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import {
  DEFAULT_ACCENT_COLOR,
  DEFAULT_CUSTOM_ACCENT,
  type AccentColor,
} from '../lib/accent-themes'
import { DEFAULT_UI_PRESET, type UiPreset } from '../lib/ui-presets'
import { type Locale, localeFromUrl, resolveInitialLocale } from '../i18n/locale'

export type { Locale }
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

  /** Show the mascot at all. When `false` the companion is not rendered. */
  mascotaEnabled: boolean
  /**
   * When `false` the mascot is a silent presence: no bubble and no voice — just
   * the character. Independent of `mascotaMuted` (which only silences the voice
   * while keeping the bubble).
   */
  mascotaSpeaks: boolean

  setLocale: (locale: Locale) => void
  setTheme: (theme: Theme) => void
  setAccentColor: (accentColor: AccentColor) => void
  setCustomAccent: (customAccent: string) => void
  setUiPreset: (uiPreset: UiPreset) => void
  setSidebarCollapsed: (collapsed: boolean) => void
  setMascotaMuted: (muted: boolean) => void
  setMascotaEnabled: (enabled: boolean) => void
  setMascotaSpeaks: (speaks: boolean) => void
}

export const usePreferences = create<PreferencesState>()(
  persist(
    (set) => ({
      locale: resolveInitialLocale(),
      theme: 'system',
      accentColor: DEFAULT_ACCENT_COLOR,
      customAccent: DEFAULT_CUSTOM_ACCENT,
      uiPreset: DEFAULT_UI_PRESET,
      sidebarCollapsed: false,
      mascotaMuted: false,
      mascotaEnabled: true,
      mascotaSpeaks: true,

      setLocale: (locale) => set({ locale }),
      setTheme: (theme) => set({ theme }),
      setAccentColor: (accentColor) => set({ accentColor }),
      setCustomAccent: (customAccent) => set({ customAccent, accentColor: 'custom' }),
      setUiPreset: (uiPreset) => set({ uiPreset }),
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
      setMascotaMuted: (muted) => set({ mascotaMuted: muted }),
      setMascotaEnabled: (enabled) => set({ mascotaEnabled: enabled }),
      setMascotaSpeaks: (speaks) => set({ mascotaSpeaks: speaks }),
    }),
    {
      name: 'skillnet-preferences',
      // Locale is the one preference a URL may override. `persist` normally hands the
      // stored value the last word, which is right for every other key here — but it
      // would make the landing site's `?lang=en` link into the demo a no-op for anyone
      // who has ever loaded the app before, and that link is the only way an English
      // reviewer gets an English demo. So: defaults, then what was stored, then an
      // explicit `?lang=` on top. Full cascade documented in `i18n/locale.ts`.
      merge: (persisted, current) => {
        const merged = { ...current, ...(persisted as Partial<PreferencesState> | undefined) }
        const requested = localeFromUrl()
        return requested ? { ...merged, locale: requested } : merged
      },
    },
  ),
)
