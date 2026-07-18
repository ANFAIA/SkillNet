import { useCallback, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from './client'
import type { DocumentRead, Paginated } from '../types'

export function useDocuments(filters?: { status?: string }) {
  return useQuery({
    queryKey: ['documents', filters ?? {}],
    queryFn: () =>
      get<Paginated<DocumentRead>>(
        `/documents${filters?.status ? `?status=${filters.status}` : ''}`,
      ),
  })
}

export interface UploadProgress {
  file: File
  progress: number // 0-100
  status: 'uploading' | 'processing' | 'ready' | 'error'
  documentId?: string
  error?: string
}

// Upload with real progress via XMLHttpRequest (fetch cannot report upload progress).
export function useUploadDocument() {
  const [uploads, setUploads] = useState<UploadProgress[]>([])
  const queryClient = useQueryClient()

  const uploadFile = useCallback(
    async (file: File): Promise<DocumentRead> => {
      const entry: UploadProgress = { file, progress: 0, status: 'uploading' }
      setUploads((prev) => [...prev, entry])

      const formData = new FormData()
      formData.append('file', file)

      try {
        const result = await new Promise<DocumentRead>((resolve, reject) => {
          const xhr = new XMLHttpRequest()

          xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
              const pct = Math.round((e.loaded / e.total) * 100)
              setUploads((prev) =>
                prev.map((u) => (u.file === file ? { ...u, progress: pct } : u)),
              )
            }
          })

          xhr.addEventListener('load', () => {
            if (xhr.status >= 200 && xhr.status < 300) {
              resolve(JSON.parse(xhr.responseText) as DocumentRead)
            } else {
              let detail = 'Upload failed'
              try {
                detail = JSON.parse(xhr.responseText).detail ?? detail
              } catch {
                /* ignore parse error */
              }
              reject(new Error(detail))
            }
          })

          xhr.addEventListener('error', () => reject(new Error('Network error')))

          xhr.open('POST', '/api/v1/documents')
          xhr.withCredentials = true
          xhr.send(formData)
        })

        setUploads((prev) =>
          prev.map((u) =>
            u.file === file
              ? { ...u, progress: 100, status: 'processing', documentId: result.id }
              : u,
          ),
        )

        queryClient.invalidateQueries({ queryKey: ['documents'] })
        return result
      } catch (err) {
        setUploads((prev) =>
          prev.map((u) =>
            u.file === file ? { ...u, status: 'error', error: (err as Error).message } : u,
          ),
        )
        throw err
      }
    },
    [queryClient],
  )

  const markReady = useCallback((documentId: string) => {
    setUploads((prev) =>
      prev.map((u) => (u.documentId === documentId ? { ...u, status: 'ready' } : u)),
    )
  }, [])

  const clearUploads = useCallback(() => setUploads([]), [])

  return { uploadFile, uploads, markReady, clearUploads }
}

export function useProcessDocument() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (documentId: string) =>
      post<{ status: string }>(`/documents/${documentId}/process`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
  })
}
