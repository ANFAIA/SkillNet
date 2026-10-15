/**
 * One line about the browser, sent with a bug report so the maintainer can reproduce it:
 * which browser, how wide the window is and which language the app is in. Nothing that
 * identifies the person.
 */
export function describeEnvironment(locale: string): string {
  const ua = typeof navigator === 'undefined' ? '' : navigator.userAgent
  const browser =
    /Edg\/(\d+)/.exec(ua)?.[0].replace('Edg/', 'Edge ') ??
    /Firefox\/(\d+)/.exec(ua)?.[0].replace('/', ' ') ??
    /Chrome\/(\d+)/.exec(ua)?.[0].replace('/', ' ') ??
    (/Version\/(\d+).*Safari/.exec(ua) ? `Safari ${/Version\/(\d+)/.exec(ua)?.[1]}` : 'unknown browser')
  const width = typeof window === 'undefined' ? 0 : window.innerWidth
  return `${browser}, ${width}px, ${locale}`
}
