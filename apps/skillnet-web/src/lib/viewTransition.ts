/**
 * Wrap a callback in the View Transitions API if available.
 * Falls back to calling the callback directly.
 */
export function withViewTransition(callback: () => void): void {
  if (typeof document !== 'undefined' && 'startViewTransition' in document) {
    ;(document as unknown as { startViewTransition: (cb: () => void) => void }).startViewTransition(callback)
  } else {
    callback()
  }
}
