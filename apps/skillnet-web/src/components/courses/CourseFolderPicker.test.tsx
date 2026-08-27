import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CourseFolderPicker } from './CourseFolderPicker'

/**
 * Putting a course in a folder that does not exist yet.
 *
 * Before this, the only place a folder could be born was the sidebar, so filing a course
 * somewhere new meant leaving the picker, creating the folder, and coming back to the row
 * to move the course. These tests hold the shortcut: name it here and the course lands in
 * it, in one gesture, without the menu sending the admin anywhere.
 */

const EXISTING_FOLDER = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const NEW_FOLDER = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'

const mockFetch = vi.fn()
const onMove = vi.fn()

function jsonResponse(status: number, body: unknown) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) })
}

/** `POST /course-folders` answers with `respond`; everything else is a 404. */
function installFetch(respond: () => Promise<unknown>) {
  mockFetch.mockImplementation((input: string, options?: RequestInit) => {
    const url = String(input)
    if (url.includes('/course-folders') && options?.method === 'POST') return respond()
    return jsonResponse(404, { detail: 'Not Found', code: 'NOT_FOUND' })
  })
}

function renderPicker(current: { id: string; name: string } | null = null) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <CourseFolderPicker
        courseTitle="Devoluciones en tienda"
        folderId={current?.id ?? null}
        folderName={current?.name ?? null}
        folders={[{ id: EXISTING_FOLDER, name: 'Operaciones' }]}
        disabled={false}
        onMove={onMove}
      />
    </QueryClientProvider>,
  )
}

async function openMenu() {
  await userEvent.click(screen.getByLabelText(/Mover Devoluciones en tienda/))
}

/** The form's submit button, whatever the final wording of its label is. */
function submitButton() {
  return screen.getByRole('button', { name: /Crear/i })
}

function nameField() {
  return screen.getByLabelText('Nombre de la carpeta')
}

/** How many `POST /course-folders` calls the component made. */
function postCount() {
  return mockFetch.mock.calls.filter(([input, options]) =>
    String(input).includes('/course-folders') && (options as RequestInit | undefined)?.method === 'POST',
  ).length
}

beforeEach(() => {
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.unstubAllGlobals()
  mockFetch.mockReset()
  onMove.mockReset()
})

describe('CourseFolderPicker — creating a folder from the menu', () => {
  it('creates the folder and leaves the course in it', async () => {
    installFetch(() => jsonResponse(201, { id: NEW_FOLDER, name: 'Atención al cliente' }))
    renderPicker()

    await openMenu()
    await userEvent.click(screen.getByRole('button', { name: /Nueva carpeta/ }))
    await userEvent.type(nameField(), 'Atención al cliente')
    await userEvent.click(submitButton())

    await waitFor(() => expect(postCount()).toBe(1))
    const [, options] = mockFetch.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === 'POST')!
    expect((options as RequestInit).body).toBe(JSON.stringify({ name: 'Atención al cliente' }))
    // Creating it is only half of what the admin asked for: the course has to end up there.
    await waitFor(() => expect(onMove).toHaveBeenCalledWith(NEW_FOLDER))
  })

  it('trims the name before sending it, as the server would', async () => {
    installFetch(() => jsonResponse(201, { id: NEW_FOLDER, name: 'Almacén' }))
    renderPicker()

    await openMenu()
    await userEvent.click(screen.getByRole('button', { name: /Nueva carpeta/ }))
    await userEvent.type(nameField(), '  Almacén  ')
    await userEvent.click(submitButton())

    await waitFor(() => expect(postCount()).toBe(1))
    const [, options] = mockFetch.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === 'POST')!
    expect((options as RequestInit).body).toBe(JSON.stringify({ name: 'Almacén' }))
  })

  it('shows what the server said about a name already taken, and does not move the course', async () => {
    // The unique index is `(org_id, lower(name))`: "operaciones" collides with "Operaciones".
    installFetch(() => jsonResponse(409, { detail: 'Ya existe una carpeta con ese nombre.', code: 'CONFLICT' }))
    renderPicker()

    await openMenu()
    await userEvent.click(screen.getByRole('button', { name: /Nueva carpeta/ }))
    await userEvent.type(nameField(), 'operaciones')
    await userEvent.click(submitButton())

    expect(await screen.findByRole('alert')).toHaveTextContent('Ya existe una carpeta con ese nombre.')
    expect(onMove).not.toHaveBeenCalled()
    // The name stays on screen so the admin can edit it instead of typing it again.
    expect(nameField()).toHaveValue('operaciones')
  })

  it('refuses to send an empty or blank name', async () => {
    installFetch(() => jsonResponse(201, { id: NEW_FOLDER, name: 'x' }))
    renderPicker()

    await openMenu()
    await userEvent.click(screen.getByRole('button', { name: /Nueva carpeta/ }))
    expect(submitButton()).toBeDisabled()

    await userEvent.type(nameField(), '   ')
    expect(submitButton()).toBeDisabled()
    expect(postCount()).toBe(0)
  })

  it('caps the name at the 120 characters the server accepts', async () => {
    installFetch(() => jsonResponse(201, { id: NEW_FOLDER, name: 'x' }))
    renderPicker()

    await openMenu()
    await userEvent.click(screen.getByRole('button', { name: /Nueva carpeta/ }))
    expect(nameField()).toHaveAttribute('maxLength', '120')
  })

  it('creates one folder, not two, when the button is clicked twice', async () => {
    // The server has a known race on the unique index, so a double submit is not merely
    // redundant: it can leave two folders with the same name.
    let release: (() => void) | undefined
    installFetch(() => new Promise<unknown>((resolve) => {
      release = () => resolve({ ok: true, status: 201, json: () => Promise.resolve({ id: NEW_FOLDER, name: 'Calidad' }) })
    }))
    renderPicker()

    await openMenu()
    await userEvent.click(screen.getByRole('button', { name: /Nueva carpeta/ }))
    await userEvent.type(nameField(), 'Calidad')
    const submit = submitButton()
    await userEvent.click(submit)
    await userEvent.click(submit)

    expect(postCount()).toBe(1)
    release?.()
    await waitFor(() => expect(onMove).toHaveBeenCalledWith(NEW_FOLDER))
    expect(postCount()).toBe(1)
  })

  it('puts the keyboard in the name field as soon as the form opens', async () => {
    installFetch(() => jsonResponse(201, { id: NEW_FOLDER, name: 'x' }))
    renderPicker()

    await openMenu()
    await userEvent.click(screen.getByRole('button', { name: /Nueva carpeta/ }))
    expect(nameField()).toHaveFocus()
  })

  it('forgets a half-typed name when the menu is closed and reopened', async () => {
    installFetch(() => jsonResponse(201, { id: NEW_FOLDER, name: 'x' }))
    renderPicker()

    await openMenu()
    await userEvent.click(screen.getByRole('button', { name: /Nueva carpeta/ }))
    await userEvent.type(nameField(), 'a medias')
    await openMenu()
    await openMenu()

    expect(screen.queryByLabelText('Nombre de la carpeta')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Nueva carpeta/ })).toBeInTheDocument()
  })
})

/**
 * The open menu used to be painted through by the folder chips of the rows underneath it.
 * Neither the rows nor the buttons are positioned, so the panel wins over those by being
 * positioned at all — but every *other* picker carried `relative` unconditionally, and a
 * positioned element later in the DOM paints above an earlier one. The rules below are
 * what keeps that from coming back without reaching for a z-index.
 */
describe('CourseFolderPicker — the open panel stays on top', () => {
  function details() {
    return document.querySelector('details') as HTMLDetailsElement
  }

  it('is only a positioned element while it is open', () => {
    renderPicker()
    // `open:relative`, never a bare `relative`: a closed picker in a row below must not
    // join the positioned layer, or its chip paints over the panel opened above it.
    expect(details().className).toContain('open:relative')
    expect(details().className.split(/\s+/)).not.toContain('relative')
  })

  it('never resorts to a z-index', () => {
    renderPicker()
    expect(details().outerHTML).not.toMatch(/\bz-(?:\d|\[)/)
  })

  it('shares one disclosure group so two menus cannot be open at once', () => {
    // There is no click-outside handler: without the shared `name`, opening a second
    // picker leaves the first one open, and the later one paints over it again.
    renderPicker()
    expect(details()).toHaveAttribute('name', 'course-folder-picker')
  })
})

describe('CourseFolderPicker — the options that were already there', () => {
  it('still moves the course to an existing folder', async () => {
    installFetch(() => jsonResponse(201, { id: NEW_FOLDER, name: 'x' }))
    renderPicker()

    await openMenu()
    await userEvent.click(screen.getByRole('button', { name: 'Operaciones' }))

    expect(onMove).toHaveBeenCalledWith(EXISTING_FOLDER)
    expect(postCount()).toBe(0)
  })

  it('still marks the current folder and offers the way out of it', async () => {
    installFetch(() => jsonResponse(201, { id: NEW_FOLDER, name: 'x' }))
    renderPicker({ id: EXISTING_FOLDER, name: 'Operaciones' })

    await openMenu()
    expect(screen.getByRole('button', { name: /Operaciones/ })).toHaveAttribute('aria-current', 'true')

    await userEvent.click(screen.getByRole('button', { name: 'Sacar de la carpeta' }))
    expect(onMove).toHaveBeenCalledWith(null)
  })
})
