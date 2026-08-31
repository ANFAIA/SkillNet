import { useRef, useState } from 'react'
import type { ChangeEvent, DragEvent, ReactNode } from 'react'
import { useIntl } from 'react-intl'

export interface FileUploadZoneProps {
  accept: string // e.g. '.pdf,.docx'
  maxFiles?: number
  maxSizeMB?: number
  onFilesSelected: (files: File[]) => void
  children?: ReactNode
}

function UploadIcon() {
  return (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="17 8 12 3 7 8" />
      <line x1="12" y1="3" x2="12" y2="15" />
    </svg>
  )
}

export function FileUploadZone({
  accept,
  maxFiles = 1,
  maxSizeMB = 20,
  onFilesSelected,
  children,
}: FileUploadZoneProps) {
  const intl = useIntl()
  const [isDragOver, setIsDragOver] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const inputRef = useRef<HTMLInputElement>(null)

  function validateFiles(files: FileList | File[]): File[] {
    const valid: File[] = []
    const newErrors: string[] = []
    const fileArray = Array.from(files)

    if (fileArray.length > maxFiles) {
      newErrors.push(intl.formatMessage({ id: 'upload.tooManyFiles' }, { count: maxFiles }))
      setErrors(newErrors)
      return []
    }

    const allowed = accept.split(',').map((ext) => ext.trim().toLowerCase())

    for (const file of fileArray) {
      const ext = '.' + (file.name.split('.').pop()?.toLowerCase() ?? '')
      if (!allowed.includes(ext)) {
        newErrors.push(intl.formatMessage({ id: 'upload.unsupportedType' }, { name: file.name }))
        continue
      }
      if (file.size > maxSizeMB * 1024 * 1024) {
        newErrors.push(
          intl.formatMessage({ id: 'upload.tooLarge' }, { name: file.name, size: maxSizeMB }),
        )
        continue
      }
      valid.push(file)
    }

    setErrors(newErrors)
    return valid
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault()
    setIsDragOver(false)
    const valid = validateFiles(e.dataTransfer.files)
    if (valid.length) onFilesSelected(valid)
  }

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    if (!e.target.files?.length) return
    const valid = validateFiles(e.target.files)
    if (valid.length) onFilesSelected(valid)
    e.target.value = ''
  }

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setIsDragOver(true)
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-lg py-10 px-4 text-center cursor-pointer transition-colors ${
          isDragOver ? 'border-primary bg-primary-subtle' : 'border-border hover:border-primary/40'
        }`}
      >
        {children ?? (
          <div className="flex flex-col items-center gap-2">
            <span className="text-text-muted">
              <UploadIcon />
            </span>
            <p className="text-sm text-text-secondary">
              {intl.formatMessage(
                { id: 'upload.dropPrompt' },
                {
                  browse: (
                    <span key="browse" className="text-primary font-medium">
                      {intl.formatMessage({ id: 'upload.browse' })}
                    </span>
                  ),
                },
              )}
            </p>
            <p className="text-xs text-text-muted">
              {intl.formatMessage(
                { id: 'upload.limits' },
                { formats: accept.replace(/\./g, '').toUpperCase(), size: maxSizeMB },
              )}
            </p>
          </div>
        )}
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          multiple={maxFiles > 1}
          onChange={handleChange}
          className="hidden"
        />
      </div>

      {errors.length > 0 && (
        <div className="mt-2 space-y-1">
          {errors.map((err, i) => (
            <p key={i} className="text-xs text-danger">
              {err}
            </p>
          ))}
        </div>
      )}
    </div>
  )
}
