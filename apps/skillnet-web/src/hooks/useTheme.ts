import { useEffect } from 'react'
import { usePreferences } from '../stores/preferences'
import type { Theme } from '../stores/preferences'

export type ResolvedTheme = 'light' | 'dark'

function systemPrefersDark(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
  )
}

/** The concrete light|dark actually painted for a stored preference. */
export function resolveTheme(theme: Theme): ResolvedTheme {
  if (theme === 'system') return systemPrefersDark() ? 'dark' : 'light'
  return theme
}

/**
 * Writes the preference onto <html>. An explicit choice sets `data-theme`; the
 * `system` choice *removes* it so the `@media (prefers-color-scheme)` block in
 * index.css drives the palette (and an explicit `data-theme="light"` beats the
 * OS because that media rule is scoped `:not([data-theme="light"])`).
 *
 * A transient `.theme-switching` class rides along for ~2 RAFs. While it is set,
 * index.css suppresses every transition, so swapping the tokens repaints in one
 * frame instead of a page-wide colour cross-fade. It is removed on the second
 * RAF — after the new palette has painted.
 */
export function applyTheme(theme: Theme) {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  root.classList.add('theme-switching')

  if (theme === 'light' || theme === 'dark') {
    root.dataset.theme = theme
  } else {
    delete root.dataset.theme
  }

  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      root.classList.remove('theme-switching')
    })
  })
}

/**
 * Keeps <html> in sync with the persisted theme preference and exposes the
 * controls. Call once at the app root to install the effect; call anywhere to
 * read/set the theme (it is backed by the shared preferences store).
 */
export function useTheme() {
  const theme = usePreferences((s) => s.theme)
  const setTheme = usePreferences((s) => s.setTheme)

  // Mirror the stored preference onto the document.
  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  // While on `system`, follow live OS changes.
  useEffect(() => {
    if (theme !== 'system') return
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => applyTheme('system')
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [theme])

  return {
    theme,
    resolvedTheme: resolveTheme(theme),
    setTheme,
    toggle: () => setTheme(resolveTheme(theme) === 'dark' ? 'light' : 'dark'),
  }
}
