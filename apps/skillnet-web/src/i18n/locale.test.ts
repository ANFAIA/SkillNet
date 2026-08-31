/**
 * The demo has to open in the language the link asked for.
 *
 * The bug this locks out: the store's initial locale was a literal `'es'`, so the landing
 * site's `?lang=en` link into the public demo opened in Spanish and an English reviewer
 * could not follow a single screen. Order and normalisation are both load-bearing — see
 * the cascade in `locale.ts`.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  DEFAULT_LOCALE,
  localeFromSearch,
  normalizeLocale,
  resolveInitialLocale,
} from './locale'

/** Point `window.location.search` and `navigator.languages` at one scenario. */
function browsing(search: string, languages: string[]) {
  vi.spyOn(window, 'location', 'get').mockReturnValue({
    ...window.location,
    search,
  } as Location)
  vi.spyOn(navigator, 'languages', 'get').mockReturnValue(languages)
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('normalizeLocale', () => {
  it('reduces a regional tag to the language we serve', () => {
    for (const tag of ['en', 'en-US', 'en_GB', 'EN', ' en-us ']) {
      expect(normalizeLocale(tag)).toBe('en')
    }
    for (const tag of ['es', 'es-ES', 'es-419', 'ES']) {
      expect(normalizeLocale(tag)).toBe('es')
    }
  })

  it('refuses anything we have no catalogue for', () => {
    // `null`, not the default: the caller decides what an unusable value falls back to,
    // and a French speaker asked for French, not for Spanish.
    for (const tag of ['fr', 'pt-BR', 'english', '', null, undefined]) {
      expect(normalizeLocale(tag)).toBeNull()
    }
  })
})

describe('localeFromSearch', () => {
  it('reads ?lang=', () => {
    expect(localeFromSearch('?lang=en')).toBe('en')
    expect(localeFromSearch('?utm_source=x&lang=es-ES')).toBe('es')
  })

  it('is null when the parameter is absent or unusable', () => {
    expect(localeFromSearch('')).toBeNull()
    expect(localeFromSearch('?locale=en')).toBeNull()
    expect(localeFromSearch('?lang=fr')).toBeNull()
  })
})

describe('resolveInitialLocale', () => {
  it('lets an explicit ?lang= beat the browser', () => {
    browsing('?lang=en', ['es-ES', 'es'])
    expect(resolveInitialLocale()).toBe('en')
  })

  it('falls to the browser when the URL says nothing', () => {
    browsing('', ['en-GB', 'en'])
    expect(resolveInitialLocale()).toBe('en')
  })

  it('skips browser languages it cannot serve', () => {
    browsing('', ['fr-FR', 'de', 'en-US'])
    expect(resolveInitialLocale()).toBe('en')
  })

  it('ends at the default when nothing usable is on offer', () => {
    browsing('?lang=fr', ['fr-FR', 'de'])
    expect(resolveInitialLocale()).toBe(DEFAULT_LOCALE)
  })
})
