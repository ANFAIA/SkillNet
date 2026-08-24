import { useState, type FormEvent } from 'react'
import { useIntl } from 'react-intl'
import { Button, Card, CardTitle, Input } from '../ui'
import { ApiError } from '../../api/client'
import { useChangeEmail, useChangePassword, useDeleteAccount } from '../../api/users'
import { useLogout } from '../../api/auth'
import { useAuth, useWorkspaceMode } from '../../hooks/useAuth'

function errorMessage(err: unknown, intl: ReturnType<typeof useIntl>, fallbackId: string): string {
  if (err instanceof ApiError) return err.body.detail
  return intl.formatMessage({ id: fallbackId })
}

/**
 * Self-service account management: change password, change email, and (in an
 * individual workspace only) delete the account. Shared between admin Settings
 * and the employee Learning Preferences page — same forms either way, there is
 * nothing role-specific about "what is my password".
 */
export function AccountSection() {
  return (
    <div className="space-y-4">
      <ChangePasswordCard />
      <ChangeEmailCard />
      <DeleteAccountCard />
    </div>
  )
}

function ChangePasswordCard() {
  const intl = useIntl()
  const mutation = useChangePassword()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [touched, setTouched] = useState(false)
  const passwordOk = newPassword.length >= 8
  const passwordError = touched && newPassword.length > 0 && !passwordOk

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!currentPassword || !passwordOk) return
    try {
      await mutation.mutateAsync({ current_password: currentPassword, new_password: newPassword })
      setCurrentPassword('')
      setNewPassword('')
      setTouched(false)
    } catch {
      // Surfaced below via mutation.error.
    }
  }

  return (
    <Card>
      <CardTitle>{intl.formatMessage({ id: 'account.password.title' })}</CardTitle>
      <p className="mt-1 text-sm text-text-secondary">
        {intl.formatMessage({ id: 'account.password.description' })}
      </p>
      <form onSubmit={handleSubmit} className="mt-4 space-y-3 max-w-sm">
        <Input
          label={intl.formatMessage({ id: 'account.password.current' })}
          type="password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          autoComplete="current-password"
        />
        <div>
          <Input
            label={intl.formatMessage({ id: 'account.password.new' })}
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            onBlur={() => setTouched(true)}
            autoComplete="new-password"
            error={passwordError ? intl.formatMessage({ id: 'setup.passwordHint' }) : undefined}
            aria-invalid={passwordError || undefined}
          />
          {!passwordError && newPassword.length > 0 && passwordOk && (
            <p className="mt-1 flex items-center gap-1 text-xs text-success">
              <span aria-hidden>✓</span>
              {intl.formatMessage({ id: 'setup.passwordOk' })}
            </p>
          )}
        </div>
        {mutation.isError && (
          <p className="text-sm text-danger" role="alert">
            {errorMessage(mutation.error, intl, 'account.password.error')}
          </p>
        )}
        {mutation.isSuccess && (
          <p className="text-sm text-success">{intl.formatMessage({ id: 'account.password.success' })}</p>
        )}
        <Button
          type="submit"
          disabled={!currentPassword || !passwordOk || mutation.isPending}
        >
          {mutation.isPending
            ? intl.formatMessage({ id: 'account.password.saving' })
            : intl.formatMessage({ id: 'account.password.submit' })}
        </Button>
      </form>
    </Card>
  )
}

function ChangeEmailCard() {
  const intl = useIntl()
  const { user } = useAuth()
  const mutation = useChangeEmail()
  const [newEmail, setNewEmail] = useState(user?.email ?? '')
  const [currentPassword, setCurrentPassword] = useState('')

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!newEmail || !currentPassword) return
    try {
      await mutation.mutateAsync({ new_email: newEmail, current_password: currentPassword })
      setCurrentPassword('')
    } catch {
      // Surfaced below via mutation.error.
    }
  }

  return (
    <Card>
      <CardTitle>{intl.formatMessage({ id: 'account.email.title' })}</CardTitle>
      <p className="mt-1 text-sm text-text-secondary">
        {intl.formatMessage({ id: 'account.email.description' })}
      </p>
      <form onSubmit={handleSubmit} className="mt-4 space-y-3 max-w-sm">
        <Input
          label={intl.formatMessage({ id: 'account.email.new' })}
          type="email"
          value={newEmail}
          onChange={(e) => setNewEmail(e.target.value)}
          autoComplete="email"
        />
        <Input
          label={intl.formatMessage({ id: 'account.password.current' })}
          type="password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          autoComplete="current-password"
        />
        {mutation.isError && (
          <p className="text-sm text-danger" role="alert">
            {errorMessage(mutation.error, intl, 'account.email.error')}
          </p>
        )}
        {mutation.isSuccess && (
          <p className="text-sm text-success">{intl.formatMessage({ id: 'account.email.success' })}</p>
        )}
        <Button type="submit" disabled={!newEmail || !currentPassword || mutation.isPending}>
          {mutation.isPending
            ? intl.formatMessage({ id: 'account.email.saving' })
            : intl.formatMessage({ id: 'account.email.submit' })}
        </Button>
      </form>
    </Card>
  )
}

/**
 * Individual workspace only — server-enforced too (`require_individual_workspace`,
 * 404 in an organization). An organization admin has no self-delete path: deleting
 * them would orphan the org, which needs an explicit ownership-transfer flow that
 * does not exist yet. Hidden here is UX; the 404 is the real guard.
 */
function DeleteAccountCard() {
  const intl = useIntl()
  const workspaceMode = useWorkspaceMode()
  const mutation = useDeleteAccount()
  const logout = useLogout()
  const [password, setPassword] = useState('')

  if (workspaceMode !== 'individual') return null

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!password) return
    if (!window.confirm(intl.formatMessage({ id: 'account.delete.confirm' }))) return
    try {
      await mutation.mutateAsync({ current_password: password })
      logout.mutate()
    } catch {
      // Surfaced below via mutation.error.
    }
  }

  return (
    <Card className="border-danger/30">
      <CardTitle>{intl.formatMessage({ id: 'account.delete.title' })}</CardTitle>
      <p className="mt-1 text-sm text-text-secondary">
        {intl.formatMessage({ id: 'account.delete.description' })}
      </p>
      <form onSubmit={handleSubmit} className="mt-4 space-y-3 max-w-sm">
        <Input
          label={intl.formatMessage({ id: 'account.password.current' })}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
        {mutation.isError && (
          <p className="text-sm text-danger" role="alert">
            {errorMessage(mutation.error, intl, 'account.delete.error')}
          </p>
        )}
        <Button type="submit" variant="danger" disabled={!password || mutation.isPending}>
          {mutation.isPending
            ? intl.formatMessage({ id: 'account.delete.saving' })
            : intl.formatMessage({ id: 'account.delete.submit' })}
        </Button>
      </form>
    </Card>
  )
}
