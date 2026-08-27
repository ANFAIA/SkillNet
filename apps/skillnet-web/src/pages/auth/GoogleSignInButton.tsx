import { useIntl } from 'react-intl'

/**
 * "Continue with Google".
 *
 * A plain link and not a `fetch`, on purpose: the OAuth authorization code flow is a
 * full-page navigation to Google and back. An XHR cannot follow it — the browser has
 * to leave the app, and the session cookie the callback sets has to arrive as a real
 * `Set-Cookie` on a top-level response.
 *
 * `AGENTS.md`: no authentication logic in the frontend. There is none here — this is
 * a link to a backend route, and every decision about who may sign in is made there.
 */
export function GoogleSignInButton({ disabled = false }: { disabled?: boolean }) {
  const intl = useIntl()
  const label = intl.formatMessage({ id: 'login.google' })

  return (
    <a
      href="/api/v1/auth/google/authorize"
      aria-disabled={disabled || undefined}
      className={[
        'flex w-full items-center justify-center gap-3 rounded-lg border border-border',
        'bg-surface px-4 py-2.5 text-sm font-medium text-text transition-colors',
        disabled ? 'pointer-events-none opacity-50' : 'hover:bg-bg-subtle',
      ].join(' ')}
    >
      <GoogleMark />
      {label}
    </a>
  )
}

/** Google's four-colour "G". The colours are the brand's and are fixed by its
 *  guidelines, so they stay literal rather than becoming theme tokens. */
function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.81.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18Z"
      />
      <path
        fill="#FBBC05"
        d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33Z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.9 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58Z"
      />
    </svg>
  )
}
