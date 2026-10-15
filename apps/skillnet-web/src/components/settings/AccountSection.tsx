import { useState, type FormEvent } from 'react'
import { useIntl } from 'react-intl'
import { Button, Input } from '../ui'
import { SettingsWindowRow } from './SettingsWindowRow'
import { useChangeEmail, useChangePassword, useDeleteAccount } from '../../api/users'
import { useLogout } from '../../api/auth'
import { useAuth, useWorkspaceMode } from '../../hooks/useAuth'
import { apiErrorMessage } from '../../lib/apiErrors'

/**
 * Self-service account management: change password, change email, and (in an
 * individual workspace only) delete the account. Shared between admin Settings
 * and the employee Learning Preferences page — same rows either way, there is
 * nothing role-specific about "what is my password".
 *
 * Each one is a quiet row; the form lives in a window that opens from its button, so the page
 * is not six open fields that almost nobody needs.
 */
export function AccountSection() {
  const intl = useIntl()
  const workspaceMode = useWorkspaceMode()
  return (
    <div>
      <SettingsWindowRow
        title={intl.formatMessage({ id: 'account.password.title' })}
        action={intl.formatMessage({ id: 'account.change' })}
        windowTitle={intl.formatMessage({ id: 'account.password.title' })}
      >
        <ChangePasswordForm />
      </SettingsWindowRow>
      <SettingsWindowRow
        title={intl.formatMessage({ id: 'account.email.title' })}
        action={intl.formatMessage({ id: 'account.change' })}
        windowTitle={intl.formatMessage({ id: 'account.email.title' })}
      >
        <ChangeEmailForm />
      </SettingsWindowRow>
      {workspaceMode === 'individual' && (
        <SettingsWindowRow
          title={intl.formatMessage({ id: 'account.delete.title' })}
          action={intl.formatMessage({ id: 'account.delete.action' })}
          windowTitle={intl.formatMessage({ id: 'account.delete.title' })}
          tone="danger"
        >
          <DeleteAccountForm />
        </SettingsWindowRow>
      )}
    </div>
  )
}

function ChangePasswordForm() {
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
    <>
      <form onSubmit={handleSubmit} className="space-y-3">
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
            {apiErrorMessage(intl, mutation.error, 'account.password.error')}
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
    </>
  )
}

function ChangeEmailForm() {
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
    <>
      <form onSubmit={handleSubmit} className="space-y-3">
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
            {apiErrorMessage(intl, mutation.error, 'account.email.error')}
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
    </>
  )
}

/**
 * Individual workspace only — server-enforced too (`require_individual_workspace`,
 * 404 in an organization). An organization admin has no self-delete path: deleting
 * them would orphan the org, which needs an explicit ownership-transfer flow that
 * does not exist yet. Hidden here is UX; the 404 is the real guard.
 */
function DeleteAccountForm() {
  const intl = useIntl()
  const mutation = useDeleteAccount()
  const logout = useLogout()
  const [password, setPassword] = useState('')

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
    <>
      <p className="mb-3 text-sm text-text-secondary">
        {intl.formatMessage({ id: 'account.delete.description' })}
      </p>
      <form onSubmit={handleSubmit} className="space-y-3">
        <Input
          label={intl.formatMessage({ id: 'account.password.current' })}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
        {mutation.isError && (
          <p className="text-sm text-danger" role="alert">
            {apiErrorMessage(intl, mutation.error, 'account.delete.error')}
          </p>
        )}
        <Button type="submit" variant="danger" disabled={!password || mutation.isPending}>
          {mutation.isPending
            ? intl.formatMessage({ id: 'account.delete.saving' })
            : intl.formatMessage({ id: 'account.delete.submit' })}
        </Button>
      </form>
    </>
  )
}
