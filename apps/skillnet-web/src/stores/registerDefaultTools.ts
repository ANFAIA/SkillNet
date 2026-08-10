import { useEffect } from 'react'
import { registerTool } from '../lib/toolRegistry'
import { usePreferences } from './preferences'
import type { Locale } from './preferences'

/**
 * Registers the default frontend tools so the AI agent can modify preferences.
 * Call this once at the app root (e.g., in App.tsx).
 */
export function useRegisterDefaultTools() {
  const { setLocale, setSidebarCollapsed, setTheme } = usePreferences()

  useEffect(() => {
    registerTool('set_locale', (args) => {
      const locale = args.locale as Locale
      if (locale === 'es' || locale === 'en') setLocale(locale)
    })

    registerTool('set_sidebar_collapsed', (args) => {
      setSidebarCollapsed(Boolean(args.collapsed))
    })

    registerTool('set_theme', (args) => {
      const theme = args.theme
      if (theme === 'light' || theme === 'dark' || theme === 'system') setTheme(theme)
    })
  }, [setLocale, setSidebarCollapsed, setTheme])
}
