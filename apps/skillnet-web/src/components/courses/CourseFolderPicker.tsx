import { useRef, useState } from 'react'
import { useIntl } from 'react-intl'

type Folder = { id: string; name: string }

type CourseFolderPickerProps = {
  courseTitle: string
  folderId: string | null | undefined
  folderName: string | null | undefined
  folders: Folder[]
  disabled: boolean
  onMove: (folderId: string | null) => void
}

function FolderIcon() {
  return <svg aria-hidden="true" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" /></svg>
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

export function CourseFolderPicker({ courseTitle, folderId, folderName, folders, disabled, onMove }: CourseFolderPickerProps) {
  const intl = useIntl()
  const detailsRef = useRef<HTMLDetailsElement>(null)
  const [open, setOpen] = useState(false)

  function choose(nextFolderId: string | null) {
    detailsRef.current?.removeAttribute('open')
    if (nextFolderId !== (folderId ?? null)) onMove(nextFolderId)
  }

  return (
    <details ref={detailsRef} className="group relative" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary
        aria-label={intl.formatMessage({ id: 'content.moveCourse' }, { title: courseTitle })}
        className="flex cursor-pointer list-none items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium text-text-secondary hover:bg-bg-muted hover:text-text [&::-webkit-details-marker]:hidden"
      >
        <FolderIcon />
        <span className="max-w-32 truncate">{folderName ?? intl.formatMessage({ id: 'content.folderUnorganized' })}</span>
        <ChevronDown open={open} />
      </summary>
      <div className="absolute right-0 z-30 mt-1 w-56 rounded-lg border border-border bg-surface p-1 shadow-md">
        <p className="px-2 py-1.5 text-xs text-text-muted">{intl.formatMessage({ id: 'content.moveTo' })}</p>
        <button type="button" disabled={disabled} onClick={() => choose(null)} className="block w-full rounded-md px-2 py-2 text-left text-sm text-text-secondary hover:bg-bg-muted hover:text-text disabled:opacity-50">{intl.formatMessage({ id: 'content.folderUnorganized' })}</button>
        {folders.map((folder) => (
          <button key={folder.id} type="button" disabled={disabled} onClick={() => choose(folder.id)} className="block w-full rounded-md px-2 py-2 text-left text-sm text-text-secondary hover:bg-bg-muted hover:text-text disabled:opacity-50">
            {folder.name}{folder.id === folderId ? ` · ${intl.formatMessage({ id: 'content.currentFolder' })}` : ''}
          </button>
        ))}
      </div>
    </details>
  )
}
