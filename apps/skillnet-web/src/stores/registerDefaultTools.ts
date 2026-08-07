import { useEffect } from 'react'
import { registerTool } from '../lib/toolRegistry'
import { usePreferences } from './preferences'
import type { Locale, Theme } from './preferences'

/**
 * Registers the default frontend tools so the AI agent can modify preferences.
 * Call this once at the app root (e.g., in App.tsx).
 */
export function useRegisterDefaultTools() {
  const { setLocale, setTheme, setSidebarCollapsed } = usePreferences()

  useEffect(() => {
    registerTool('set_locale', (args) => {
      const locale = args.locale as Locale
      if (locale === 'es' || locale === 'en') setLocale(locale)
    })

    registerTool('set_theme', (args) => {
      const theme = args.theme as Theme
      if (theme === 'light' || theme === 'dark' || theme === 'system') setTheme(theme)
    })

    registerTool('set_sidebar_collapsed', (args) => {
      setSidebarCollapsed(Boolean(args.collapsed))
    })
  }, [setLocale, setTheme, setSidebarCollapsed])
}
