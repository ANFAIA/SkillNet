/**
 * Which language the app opens in, before anybody has touched the selector.
 *
 * The store shipped a hardcoded `'es'`, so the landing site's `?lang=en` link into the
 * public demo opened in Spanish and an English reader could not follow the demo at all.
 * The cascade is ordered by how *deliberate* each signal is, strongest first:
 *
 *   1. **`?lang=` in the URL** — a language asked for now, in this navigation. It
 *      outranks the persisted value on purpose (see `merge` in
 *      `stores/preferences.ts`): a shared link has to open in the language it names even
 *      on a browser that once chose another one, or the parameter is decoration.
 *   2. **The persisted preference** — the visitor's own past choice. Restored by
 *      zustand's `persist`, so it is applied by the middleware and not by this module.
 *   3. **`navigator.language`** — the browser's guess. Better than a coin toss on a
 *      first visit, and never a stated preference, so it loses to both of the above.
 *   4. **`'es'`** — the project's original language, and the only one every message id is
 *      guaranteed to have.
 */

export const SUPPORTED_LOCALES = ['es', 'en'] as const

export type Locale = (typeof SUPPORTED_LOCALES)[number]

export const DEFAULT_LOCALE: Locale = 'es'

/** Query parameter the landing site uses to open the demo in a language. */
export const LOCALE_PARAM = 'lang'

/**
 * A locale tag reduced to one we actually have, or `null`.
 *
 * `en-US`, `en_GB` and `EN` are all `en`; `fr` is nothing, because falling back to the
 * default is honest and picking the nearest neighbour is not.
 */
export function normalizeLocale(value: string | null | undefined): Locale | null {
  if (!value) return null
  const base = value.trim().toLowerCase().split(/[-_]/)[0]
  return (SUPPORTED_LOCALES as readonly string[]).includes(base) ? (base as Locale) : null
}

/** The `?lang=` of a query string, when it names a locale we have. */
export function localeFromSearch(search: string): Locale | null {
  return normalizeLocale(new URLSearchParams(search).get(LOCALE_PARAM))
}

/** The current document's `?lang=`. Safe to call where there is no `window`. */
export function localeFromUrl(): Locale | null {
  if (typeof window === 'undefined') return null
  return localeFromSearch(window.location.search)
}

/** The first of the browser's preferred languages we can serve. */
function localeFromBrowser(): Locale | null {
  if (typeof navigator === 'undefined') return null
  const candidates = navigator.languages?.length ? navigator.languages : [navigator.language]
  for (const candidate of candidates) {
    const locale = normalizeLocale(candidate)
    if (locale) return locale
  }
  return null
}

/**
 * Steps 1, 3 and 4 of the cascade — the value the store starts with.
 *
 * Step 2 is missing here because it is not ours to apply: `persist` rehydrates the stored
 * preference over this initial state, and the `merge` beside it puts step 1 back on top.
 */
export function resolveInitialLocale(): Locale {
  return localeFromUrl() ?? localeFromBrowser() ?? DEFAULT_LOCALE
}
