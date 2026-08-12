import { useEffect } from 'react'
import { usePreferences } from '../stores/preferences'
import type { Theme } from '../stores/preferences'
import type { AccentColor } from '../lib/accent-themes'
import type { UiPreset } from '../lib/ui-presets'

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

  // Remove after the swap has painted. Double-rAF is the happy path, but rAF is
  // throttled/paused on a backgrounded tab — and if it never fires, the class
  // sticks and `transition: none !important` silently disables every transition
  // in the app. A setTimeout is the fallback that fires even when rAF is frozen;
  // whichever runs first clears it (removing a class twice is a no-op).
  const clear = () => root.classList.remove('theme-switching')
  requestAnimationFrame(() => requestAnimationFrame(clear))
  setTimeout(clear, 150)
}

export function applyUiPreset(uiPreset: UiPreset) {
  if (typeof document === 'undefined') return
  document.documentElement.dataset.uiPreset = uiPreset
}

export function applyAccentColor(accentColor: AccentColor, customAccent: string) {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  root.dataset.accent = accentColor
  if (accentColor === 'custom') {
    root.style.setProperty('--custom-accent', customAccent)
  } else {
    root.style.removeProperty('--custom-accent')
  }
}

/**
 * Keeps <html> in sync with the persisted theme preference and exposes the
 * controls. Call once at the app root to install the effect; call anywhere to
 * read/set the theme (it is backed by the shared preferences store).
 */
export function useTheme() {
  const theme = usePreferences((s) => s.theme)
  const setTheme = usePreferences((s) => s.setTheme)
  const accentColor = usePreferences((s) => s.accentColor)
  const customAccent = usePreferences((s) => s.customAccent)
  const setAccentColor = usePreferences((s) => s.setAccentColor)
  const setCustomAccent = usePreferences((s) => s.setCustomAccent)
  const uiPreset = usePreferences((s) => s.uiPreset)
  const setUiPreset = usePreferences((s) => s.setUiPreset)

  // Mirror the stored preference onto the document.
  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  useEffect(() => {
    applyUiPreset(uiPreset)
  }, [uiPreset])

  useEffect(() => {
    applyAccentColor(accentColor, customAccent)
  }, [accentColor, customAccent])

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
    accentColor,
    customAccent,
    setAccentColor,
    setCustomAccent,
    uiPreset,
    setUiPreset,
    toggle: () => setTheme(resolveTheme(theme) === 'dark' ? 'light' : 'dark'),
  }
}
