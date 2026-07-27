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

/** One document. Used to tell the creator where a course's source came from. */
export function useDocument(documentId: string | null | undefined) {
  return useQuery({
    queryKey: ['documents', documentId],
    queryFn: () => get<DocumentRead>(`/documents/${documentId}`),
    enabled: !!documentId,
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

/** How long to wait for a synthesised source to finish ingesting, and how often to ask. */
const INGEST_POLL_MS = 1000
const INGEST_TIMEOUT_MS = 90_000

/**
 * Wait until a document is `ready`, because `POST /courses/{id}/generate` refuses
 * anything else.
 *
 * Polling and not SSE: ingestion has no event stream, it is normally a couple of
 * seconds, and adding one for this would be more moving parts than the problem has.
 * Rejects on `error` with the server's own message, and on timeout — a caller that
 * hangs forever on a stuck ingestion is worse than one that says so.
 */
export async function waitForDocumentReady(documentId: string): Promise<DocumentRead> {
  const deadline = Date.now() + INGEST_TIMEOUT_MS
  for (;;) {
    const doc = await get<DocumentRead>(`/documents/${documentId}`)
    if (doc.status === 'ready') return doc
    if (doc.status === 'error') {
      throw new Error(doc.error_message ?? 'No se pudo procesar el documento generado')
    }
    if (Date.now() > deadline) {
      throw new Error('El documento generado tarda demasiado en procesarse')
    }
    await new Promise((resolve) => setTimeout(resolve, INGEST_POLL_MS))
  }
}

/**
 * `POST /documents/from-idea` — the "desde cero" path.
 *
 * The server writes a source document from the title and the creator's description and
 * starts ingesting it, so what comes back is an ordinary `DocumentRead` in `processing`
 * whose `origin` is `'generated'`. Everything after this point is the document flow.
 */
export function useCreateSourceFromIdea() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { title: string; idea: string }) =>
      post<DocumentRead>('/documents/from-idea', body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
  })
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
