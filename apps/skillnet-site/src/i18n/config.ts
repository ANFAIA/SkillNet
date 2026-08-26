/**
 * Locale routing helpers.
 *
 * Astro's `i18n` config declares `es` as the default locale with
 * `prefixDefaultLocale: false`, so Spanish lives at the bare path (`/docs/x`)
 * and English lives one segment deeper (`/en/docs/x`). Every locale-aware
 * decision on the site derives from those two shapes, so the mapping between
 * them is written once here rather than re-derived per page.
 */

export const LOCALES = ["es", "en"] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "es";

/** localStorage key holding an explicit, user-made language choice. */
export const LANG_STORAGE_KEY = "skillnet:lang";

export function isLocale(value: unknown): value is Locale {
  return value === "es" || value === "en";
}

/** The locale a pathname belongs to, from its first segment. */
export function localeFromPath(pathname: string): Locale {
  return pathname === "/en" || pathname.startsWith("/en/") ? "en" : "es";
}

/** Strip the locale prefix, returning the shared, locale-free path. */
export function stripLocale(pathname: string): string {
  if (pathname === "/en") return "/";
  if (pathname.startsWith("/en/")) return pathname.slice(3);
  return pathname;
}

/** The path the given locale-free path takes in `locale`. */
export function localizePath(path: string, locale: Locale): string {
  const base = path.startsWith("/") ? path : `/${path}`;
  if (locale === DEFAULT_LOCALE) return base;
  return base === "/" ? "/en/" : `/en${base}`;
}

/** The equivalent of `pathname` in the other locale. */
export function alternatePath(pathname: string): string {
  const other: Locale = localeFromPath(pathname) === "en" ? "es" : "en";
  return localizePath(stripLocale(pathname), other);
}
