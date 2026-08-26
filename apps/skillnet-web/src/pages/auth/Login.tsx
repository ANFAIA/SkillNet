import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useIntl } from 'react-intl'
import { Button, Card, Input, Logo } from '../../components/ui'
import { useLogin } from '../../api/auth'
import { useCapability } from '../../api/setup'
import { useAuth } from '../../hooks/useAuth'
import { ApiError } from '../../api/client'
import { GoogleSignInButton } from './GoogleSignInButton'

/**
 * Reasons the Google callback can refuse a sign-in. The backend sends the code, never
 * the sentence: the callback is a browser redirect, so the message has to be written
 * here where the language is known.
 */
const GOOGLE_ERROR_IDS: Record<string, string> = {
  not_invited: 'login.googleNotInvited',
  email_unverified: 'login.googleEmailUnverified',
  inactive: 'login.googleInactive',
  already_linked: 'login.googleAlreadyLinked',
  cancelled: 'login.googleCancelled',
  invalid_state: 'login.googleExpired',
  not_initialized: 'login.googleNotInitialized',
}

const HOME_BY_ROLE = {
  admin: '/admin',
  employee: '/empleado',
} as const

export function Login() {
  const navigate = useNavigate()
  const intl = useIntl()
  const login = useLogin()
  const { user } = useAuth()
  const googleEnabled = useCapability('google_login')
  const [searchParams] = useSearchParams()
  const googleError = searchParams.get('google_error')

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  // If already authenticated, skip the form.
  useEffect(() => {
    if (user) navigate(HOME_BY_ROLE[user.role], { replace: true })
  }, [user, navigate])

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!email.trim() || !password || login.isPending) return
    login.mutate(
      { email: email.trim(), password },
      {
        onSuccess: (loggedIn) => {
          navigate(HOME_BY_ROLE[loggedIn.role], { replace: true })
        },
      },
    )
  }

  const googleErrorMessage = googleError
    ? intl.formatMessage({ id: GOOGLE_ERROR_IDS[googleError] ?? 'login.googleGenericError' })
    : null

  const errorMessage =
    login.error instanceof ApiError
      ? login.error.status === 400 || login.error.status === 401
        ? intl.formatMessage({ id: 'login.wrongCredentials' })
        : login.error.body.detail
      : login.error
        ? intl.formatMessage({ id: 'login.genericError' })
        : null

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card className="w-full max-w-sm bg-surface">
        <div className="flex flex-col items-center mb-6">
          <Logo size={48} className="drop-shadow" />
          <h1 className="text-lg font-semibold text-text mt-3">SkillNet</h1>
          <p className="text-sm text-text-secondary mt-0.5">{intl.formatMessage({ id: 'login.subtitle' })}</p>
        </div>

        {googleErrorMessage && (
          <p className="text-sm text-danger mb-4" role="alert">
            {googleErrorMessage}
          </p>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label={intl.formatMessage({ id: 'login.emailLabel' })}
            type="email"
            autoComplete="email"
            placeholder={intl.formatMessage({ id: 'login.emailPlaceholder' })}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={login.isPending}
          />
          <Input
            label={intl.formatMessage({ id: 'login.passwordLabel' })}
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={login.isPending}
          />

          {errorMessage && <p className="text-sm text-danger">{errorMessage}</p>}

          <Button
            type="submit"
            size="lg"
            className="w-full"
            disabled={login.isPending || !email.trim() || !password}
          >
            {login.isPending ? intl.formatMessage({ id: 'login.loggingIn' }) : intl.formatMessage({ id: 'login.submit' })}
          </Button>
        </form>

        {googleEnabled && (
          <>
            <div className="flex items-center gap-3 my-5">
              <span className="h-px flex-1 bg-border" />
              <span className="text-xs uppercase tracking-wide text-text-muted">
                {intl.formatMessage({ id: 'login.or' })}
              </span>
              <span className="h-px flex-1 bg-border" />
            </div>
            <GoogleSignInButton disabled={login.isPending} />
          </>
        )}
      </Card>
    </div>
  )
}
