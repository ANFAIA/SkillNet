import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { IntlProvider } from '../../i18n/IntlProvider'
import { AccountSection } from './AccountSection'

/**
 * The self-service account forms: change password, change email, delete
 * account. Delete is gated to an `individual` workspace both server-side
 * (`require_individual_workspace`, 404 otherwise) and here in the UI — these
 * tests pin that the UI gate actually matches, since a mismatch would either
 * show a button that always 404s or hide one that should work.
 *
 * All three cards render a field labelled "Contraseña actual", so every query
 * here is scoped with `within(card)` rather than a page-wide `getByLabelText`
 * — otherwise "found multiple elements" is not a test bug, it is the fixture
 * not matching how the page is actually laid out.
 */

const mockFetch = vi.fn()

function jsonResponse(status: number, body: unknown) {
  return Promise.resolve({
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
  })
}

function installFetch({
  workspaceMode = 'organization',
  changePasswordStatus = 200,
  changeEmailStatus = 200,
  deleteAccountStatus = 200,
}: {
  workspaceMode?: 'organization' | 'individual'
  changePasswordStatus?: number
  changeEmailStatus?: number
  deleteAccountStatus?: number
} = {}) {
  mockFetch.mockImplementation((input: string, options?: RequestInit) => {
    const url = String(input)
    const method = options?.method ?? 'GET'
    if (url.endsWith('/auth/me')) {
      return jsonResponse(200, {
        id: 'u1',
        email: 'ada@test.dev',
        full_name: 'Ada',
        role: 'admin',
        workspace_mode: workspaceMode,
      })
    }
    if (url.endsWith('/users/me/change-password') && method === 'POST') {
      return changePasswordStatus < 400
        ? jsonResponse(200, { ok: true })
        : jsonResponse(changePasswordStatus, {
            detail: 'Current password is incorrect',
            code: 'VALIDATION_ERROR',
            field: 'current_password',
          })
    }
    if (url.endsWith('/users/me/email') && method === 'PUT') {
      return changeEmailStatus < 400
        ? jsonResponse(200, {
            id: 'u1',
            email: 'new@test.dev',
            full_name: 'Ada',
            role: 'admin',
            learning_profile: 'standard',
            accessibility: {},
          })
        : jsonResponse(changeEmailStatus, {
            detail: 'A user with this email already exists',
            code: 'CONFLICT',
            field: 'email',
          })
    }
    if (url.endsWith('/users/me') && method === 'DELETE') {
      return deleteAccountStatus < 400
        ? jsonResponse(200, { ok: true })
        : jsonResponse(deleteAccountStatus, {
            detail: 'Password is incorrect',
            code: 'VALIDATION_ERROR',
            field: 'current_password',
          })
    }
    if (url.endsWith('/auth/logout')) {
      return jsonResponse(200, {})
    }
    return jsonResponse(404, { detail: 'Not Found', code: 'NOT_FOUND' })
  })
}

function renderSection() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <IntlProvider>
        <AccountSection />
      </IntlProvider>
    </QueryClientProvider>,
  )
}

/** The card is the `<h3>` title's grandparent (Card > div > h3). */
async function findCard(title: string) {
  const heading = await screen.findByRole('heading', { name: title })
  return heading.parentElement as HTMLElement
}

beforeEach(() => {
  mockFetch.mockReset()
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('AccountSection — change password', () => {
  it('submits current and new password to the change-password endpoint', async () => {
    installFetch()
    renderSection()
    const card = await findCard('Contraseña')

    await userEvent.type(within(card).getByLabelText('Contraseña actual'), 'old-password')
    await userEvent.type(within(card).getByLabelText('Contraseña nueva'), 'new-password-123')
    await userEvent.click(within(card).getByRole('button', { name: 'Cambiar contraseña' }))

    expect(await within(card).findByText('Contraseña actualizada.')).toBeInTheDocument()
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/users/me/change-password',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ current_password: 'old-password', new_password: 'new-password-123' }),
      }),
    )
  })

  it('shows the field-level validation hint for a too-short new password', async () => {
    installFetch()
    renderSection()
    const card = await findCard('Contraseña')

    await userEvent.type(within(card).getByLabelText('Contraseña nueva'), 'short')
    await userEvent.tab()

    expect(await within(card).findByText('Al menos 8 caracteres.')).toBeInTheDocument()
  })

  it('surfaces the server error when the current password is wrong', async () => {
    installFetch({ changePasswordStatus: 422 })
    renderSection()
    const card = await findCard('Contraseña')

    await userEvent.type(within(card).getByLabelText('Contraseña actual'), 'wrong')
    await userEvent.type(within(card).getByLabelText('Contraseña nueva'), 'new-password-123')
    await userEvent.click(within(card).getByRole('button', { name: 'Cambiar contraseña' }))

    expect(await within(card).findByText('Current password is incorrect')).toBeInTheDocument()
  })
})

describe('AccountSection — change email', () => {
  it('submits the new email and current password', async () => {
    installFetch()
    renderSection()
    const card = await findCard('Correo electrónico')

    const emailInput = within(card).getByLabelText('Correo nuevo')
    await userEvent.clear(emailInput)
    await userEvent.type(emailInput, 'new@test.dev')
    await userEvent.type(within(card).getByLabelText('Contraseña actual'), 'my-password')
    await userEvent.click(within(card).getByRole('button', { name: 'Cambiar correo' }))

    expect(await within(card).findByText('Correo actualizado.')).toBeInTheDocument()
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/users/me/email',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ new_email: 'new@test.dev', current_password: 'my-password' }),
      }),
    )
  })

  it('surfaces the conflict when the email is already taken', async () => {
    installFetch({ changeEmailStatus: 409 })
    renderSection()
    const card = await findCard('Correo electrónico')

    const emailInput = within(card).getByLabelText('Correo nuevo')
    await userEvent.clear(emailInput)
    await userEvent.type(emailInput, 'taken@test.dev')
    await userEvent.type(within(card).getByLabelText('Contraseña actual'), 'my-password')
    await userEvent.click(within(card).getByRole('button', { name: 'Cambiar correo' }))

    expect(await within(card).findByText('A user with this email already exists')).toBeInTheDocument()
  })
})

describe('AccountSection — delete account (workspace gating)', () => {
  it('hides the delete-account card in an organization workspace', async () => {
    installFetch({ workspaceMode: 'organization' })
    renderSection()

    // Wait for /auth/me to resolve before asserting absence.
    await screen.findByRole('heading', { name: 'Contraseña' })
    expect(screen.queryByRole('heading', { name: 'Borrar cuenta' })).toBeNull()
  })

  it('shows the delete-account card in an individual workspace and submits it', async () => {
    installFetch({ workspaceMode: 'individual' })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    renderSection()
    const card = await findCard('Borrar cuenta')

    await userEvent.type(within(card).getByLabelText('Contraseña actual'), 'my-password')
    await userEvent.click(within(card).getByRole('button', { name: 'Borrar mi cuenta' }))

    expect(window.confirm).toHaveBeenCalled()
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/v1/users/me',
      expect.objectContaining({
        method: 'DELETE',
        body: JSON.stringify({ current_password: 'my-password' }),
      }),
    )
  })

  it('does not call the API when the confirm dialog is dismissed', async () => {
    installFetch({ workspaceMode: 'individual' })
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderSection()
    const card = await findCard('Borrar cuenta')

    await userEvent.type(within(card).getByLabelText('Contraseña actual'), 'my-password')
    await userEvent.click(within(card).getByRole('button', { name: 'Borrar mi cuenta' }))

    expect(window.confirm).toHaveBeenCalled()
    expect(mockFetch).not.toHaveBeenCalledWith(
      '/api/v1/users/me',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })
})
