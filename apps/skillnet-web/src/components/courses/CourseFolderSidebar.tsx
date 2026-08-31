import { useState, type FormEvent } from 'react'
import { useIntl } from 'react-intl'
import { apiErrorMessage } from '../../lib/apiErrors'
import {
  useCreateCourseFolder,
  useDeleteCourseFolder,
  useRenameCourseFolder,
  type CourseFolder,
} from '../../api/course-folders'
import { Button, Input } from '../ui'

export type FolderFilter = 'all' | 'unorganized' | string

function FolderIcon() {
  return (
    <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
    </svg>
  )
}

function EditIcon() {
  return <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m4 20 4.5-1 11-11-3.5-3.5-11 11Z" /><path d="m14.5 6 3.5 3.5" /></svg>
}

function TrashIcon() {
  return <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7" /></svg>
}

function UsersIcon() {
  return <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" /></svg>
}

function PlusIcon() {
  return <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
}

interface CourseFolderSidebarProps {
  folders: CourseFolder[]
  selected: FolderFilter
  totalCount: number
  unorganizedCount: number
  onSelect: (folder: FolderFilter) => void
  onAssign: (folder: CourseFolder) => void
}

export function CourseFolderSidebar({ folders, selected, totalCount, unorganizedCount, onSelect, onAssign }: CourseFolderSidebarProps) {
  const intl = useIntl()
  const createFolder = useCreateCourseFolder()
  const renameFolder = useRenameCourseFolder()
  const deleteFolder = useDeleteCourseFolder()
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function submitCreate(event: FormEvent) {
    event.preventDefault()
    const name = newName.trim()
    if (!name) return
    setError(null)
    try {
      await createFolder.mutateAsync(name)
      setNewName('')
      setCreating(false)
    } catch (reason) {
      setError(apiErrorMessage(intl, reason, 'content.folderSaveError'))
    }
  }

  async function submitRename(event: FormEvent, id: string) {
    event.preventDefault()
    const name = editingName.trim()
    if (!name) return
    setError(null)
    try {
      await renameFolder.mutateAsync({ id, name })
      setEditingId(null)
    } catch (reason) {
      setError(apiErrorMessage(intl, reason, 'content.folderSaveError'))
    }
  }

  async function removeFolder(folder: CourseFolder) {
    if (!window.confirm(intl.formatMessage({ id: 'content.folderDeleteConfirm' }, { name: folder.name }))) return
    setError(null)
    try {
      await deleteFolder.mutateAsync(folder.id)
      if (selected === folder.id) onSelect('all')
    } catch (reason) {
      setError(apiErrorMessage(intl, reason, 'content.folderDeleteError'))
    }
  }

  function filterButton(value: FolderFilter, label: string, count: number | undefined) {
    const active = selected === value
    return (
      <button
        type="button"
        onClick={() => onSelect(value)}
        className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors ${active ? 'bg-primary-subtle text-primary font-medium' : 'text-text-secondary hover:bg-bg-muted hover:text-text'}`}
      >
        <FolderIcon />
        <span className="truncate flex-1">{label}</span>
        {count !== undefined && <span className="text-xs tabular-nums text-text-muted">{count}</span>}
      </button>
    )
  }

  return (
    <aside className="border border-border rounded-lg p-3" aria-label={intl.formatMessage({ id: 'content.folders' })}>
      <div className="mb-3 flex items-center justify-between gap-2 px-1">
        <h3 className="text-sm font-medium text-text">{intl.formatMessage({ id: 'content.folders' })}</h3>
        <Button type="button" variant="secondary" size="sm" onClick={() => setCreating(true)} disabled={creating}>
          <span className="flex items-center gap-1"><PlusIcon />{intl.formatMessage({ id: 'content.folderNew' })}</span>
        </Button>
      </div>
      <nav className="space-y-1">
        {filterButton('all', intl.formatMessage({ id: 'content.folderAll' }), totalCount)}
        {filterButton('unorganized', intl.formatMessage({ id: 'content.folderNone' }), unorganizedCount)}
        {folders.map((folder) => (
          <div key={folder.id} className="group">
            {editingId === folder.id ? (
              <form onSubmit={(event) => submitRename(event, folder.id)} className="space-y-2 p-1">
                <Input autoFocus value={editingName} maxLength={100} aria-label={intl.formatMessage({ id: 'content.folderName' })} onChange={(event) => setEditingName(event.target.value)} />
                <div className="flex gap-1">
                  <Button size="sm" type="submit" disabled={!editingName.trim() || renameFolder.isPending}>{intl.formatMessage({ id: 'content.folderSave' })}</Button>
                  <Button size="sm" variant="ghost" type="button" onClick={() => setEditingId(null)}>{intl.formatMessage({ id: 'content.folderCancel' })}</Button>
                </div>
              </form>
            ) : (
              <div className="flex items-center">
                <div className="flex-1 min-w-0">{filterButton(folder.id, folder.name, folder.course_count)}</div>
                <div className="flex opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-within:opacity-100 transition-opacity">
                  <button type="button" aria-label={intl.formatMessage({ id: 'content.folderAssign' }, { name: folder.name })} className="p-1.5 text-text-muted hover:text-text" onClick={() => onAssign(folder)}><UsersIcon /></button>
                  <button type="button" aria-label={intl.formatMessage({ id: 'content.folderRename' }, { name: folder.name })} className="p-1.5 text-text-muted hover:text-text" onClick={() => { setEditingId(folder.id); setEditingName(folder.name) }}><EditIcon /></button>
                  <button type="button" aria-label={intl.formatMessage({ id: 'content.folderDelete' }, { name: folder.name })} className="p-1.5 text-text-muted hover:text-danger" onClick={() => removeFolder(folder)}><TrashIcon /></button>
                </div>
              </div>
            )}
          </div>
        ))}
      </nav>
      {creating && (
        <form onSubmit={submitCreate} className="mt-3 border-t border-border pt-3 space-y-2">
          <Input autoFocus value={newName} maxLength={100} placeholder={intl.formatMessage({ id: 'content.folderName' })} onChange={(event) => setNewName(event.target.value)} />
          <div className="flex gap-1">
            <Button size="sm" type="submit" disabled={!newName.trim() || createFolder.isPending}>{intl.formatMessage({ id: 'content.folderCreate' })}</Button>
            <Button size="sm" variant="ghost" type="button" onClick={() => { setCreating(false); setNewName('') }}>{intl.formatMessage({ id: 'content.folderCancel' })}</Button>
          </div>
        </form>
      )}
      {error && <p role="alert" className="mt-3 px-2 text-xs text-danger">{error}</p>}
    </aside>
  )
}
