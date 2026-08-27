import { useRef, useState, type FormEvent } from 'react'
import { useIntl } from 'react-intl'
import { ApiError } from '../../api/client'
import { useCreateCourseFolder } from '../../api/course-folders'
import { Button, Input } from '../ui'

type Folder = { id: string; name: string }

type CourseFolderPickerProps = {
  courseTitle: string
  folderId: string | null | undefined
  folderName: string | null | undefined
  folders: Folder[]
  disabled: boolean
  onMove: (folderId: string | null) => void
}

/** The server trims the name and accepts 1..120 characters (`CourseFolderWrite`). */
const NAME_MAX_LENGTH = 120

function FolderIcon() {
  return <svg aria-hidden="true" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" /></svg>
}

function CheckIcon() {
  return <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0"><polyline points="20 6 9 17 4 12" /></svg>
}

function PlusIcon() {
  return <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0"><path d="M12 5v14M5 12h14" /></svg>
}

function ChevronDown({ open }: { open: boolean }) {
  return (
    <svg
      aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
      className={`shrink-0 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}

/**
 * Move one course between folders, or into a folder that does not exist yet.
 *
 * A course sits in zero or one folder (`courses.folder_id` is a nullable FK), so the menu
 * is a single-choice list with the current option marked — a tick and a highlight, not
 * only the word "current" tacked onto the label, which is what the admin was missing.
 *
 * Creating a folder lives here rather than only in the sidebar because the admin who
 * opens this menu has already decided where the course belongs; when that place has no
 * folder yet, sending them to the sidebar and back is the whole trip they wanted to
 * avoid. The create form is a `<form>` inside the same panel: the menu is already a
 * `<details>` disclosure holding real buttons, not a native `<select>`, so a text field
 * fits it without changing the control.
 */
export function CourseFolderPicker({ courseTitle, folderId, folderName, folders, disabled, onMove }: CourseFolderPickerProps) {
  const intl = useIntl()
  const detailsRef = useRef<HTMLDetailsElement>(null)
  const [open, setOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const createFolder = useCreateCourseFolder()
  /**
   * A second submit before React has re-rendered with `isPending` would send a second
   * POST, and the server has a known race on `(org_id, lower(name))`: two inserts that
   * cross can leave a duplicate instead of a clean 409. A ref closes the window the
   * `isPending` flag alone leaves open.
   */
  const submitting = useRef(false)
  const current = folderId ?? null
  const busy = disabled || createFolder.isPending

  function close() {
    detailsRef.current?.removeAttribute('open')
  }

  function reset() {
    setCreating(false)
    setNewName('')
    setError(null)
  }

  function choose(nextFolderId: string | null) {
    close()
    if (nextFolderId !== current) onMove(nextFolderId)
  }

  async function submitCreate(event: FormEvent) {
    event.preventDefault()
    const name = newName.trim()
    if (!name || submitting.current) return
    submitting.current = true
    setError(null)
    try {
      const folder = await createFolder.mutateAsync(name)
      close()
      reset()
      // Move without a second confirmation: the admin opened *this course's* picker and
      // named a folder for it, so "create it and leave the course somewhere else" is not
      // a state anybody asked for. The move is the same call the existing options make.
      onMove(folder.id)
    } catch (reason) {
      // 409 when a folder with that name already exists — the index is case-insensitive,
      // so "Operaciones" and "operaciones" collide. The server's own wording says which.
      setError(reason instanceof ApiError ? reason.body.detail : intl.formatMessage({ id: 'content.folderSaveError' }))
    } finally {
      submitting.current = false
    }
  }

  function option(value: string | null, label: string) {
    const isCurrent = value === current
    return (
      <button
        key={value ?? 'none'}
        type="button"
        disabled={busy}
        aria-current={isCurrent ? 'true' : undefined}
        onClick={() => choose(value)}
        className={`flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm disabled:opacity-50 ${isCurrent ? 'bg-primary-subtle font-medium text-primary' : 'text-text-secondary hover:bg-bg-muted hover:text-text'}`}
      >
        <span className="w-3.5 shrink-0">{isCurrent && <CheckIcon />}</span>
        <span className="min-w-0 flex-1 truncate">{label}</span>
        {isCurrent && <span className="shrink-0 text-xs">{intl.formatMessage({ id: 'content.currentFolder' })}</span>}
      </button>
    )
  }

  return (
    <details
      ref={detailsRef}
      className="group relative"
      onToggle={(event) => {
        setOpen(event.currentTarget.open)
        // Reopening starts clean: a half-typed name or a stale 409 from last time is not
        // something the admin left on screen on purpose.
        if (!event.currentTarget.open) reset()
      }}
    >
      <summary
        aria-label={intl.formatMessage({ id: 'content.moveCourse' }, { title: courseTitle })}
        className="flex cursor-pointer list-none items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium text-text-secondary hover:bg-bg-muted hover:text-text [&::-webkit-details-marker]:hidden"
      >
        <FolderIcon />
        <span className={`max-w-32 truncate ${folderName ? 'text-text' : 'text-text-muted italic'}`}>
          {folderName ?? intl.formatMessage({ id: 'content.folderNone' })}
        </span>
        <ChevronDown open={open} />
      </summary>
      <div className="absolute right-0 z-30 mt-1 w-56 rounded-lg border border-border bg-surface p-1 shadow-md">
        <p className="px-2 py-1.5 text-xs text-text-muted">{intl.formatMessage({ id: 'content.moveTo' })}</p>
        {/* Leaving a folder is `folder_id = null`. Named for what it does from here: an
            admin reading "no folder" while the course is in one has to guess. */}
        {option(null, intl.formatMessage({ id: current ? 'content.folderRemove' : 'content.folderNone' }))}
        {folders.map((folder) => option(folder.id, folder.name))}
        <div className="mt-1 border-t border-border pt-1">
          {creating ? (
            <form onSubmit={submitCreate} className="space-y-2 p-1">
              <Input
                autoFocus
                value={newName}
                maxLength={NAME_MAX_LENGTH}
                disabled={createFolder.isPending}
                aria-label={intl.formatMessage({ id: 'content.folderName' })}
                placeholder={intl.formatMessage({ id: 'content.folderName' })}
                onChange={(event) => setNewName(event.target.value)}
              />
              <div className="flex gap-1">
                {/* An empty (or all-whitespace) name is refused here, not by the server. */}
                <Button size="sm" type="submit" disabled={!newName.trim() || createFolder.isPending}>
                  {createFolder.isPending
                    ? intl.formatMessage({ id: 'content.folderCreating', defaultMessage: 'Creando...' })
                    : intl.formatMessage({ id: 'content.folderCreateAndMove', defaultMessage: 'Crear y mover' })}
                </Button>
                <Button size="sm" variant="ghost" type="button" disabled={createFolder.isPending} onClick={reset}>
                  {intl.formatMessage({ id: 'content.folderCancel' })}
                </Button>
              </div>
            </form>
          ) : (
            <button
              type="button"
              disabled={busy}
              onClick={() => { setError(null); setCreating(true) }}
              className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm text-text-secondary hover:bg-bg-muted hover:text-text disabled:opacity-50"
            >
              <span className="w-3.5 shrink-0"><PlusIcon /></span>
              <span className="min-w-0 flex-1 truncate">{intl.formatMessage({ id: 'content.folderNew' })}</span>
            </button>
          )}
        </div>
        {error && <p role="alert" className="px-2 pb-1.5 pt-1 text-xs text-danger">{error}</p>}
      </div>
    </details>
  )
}
