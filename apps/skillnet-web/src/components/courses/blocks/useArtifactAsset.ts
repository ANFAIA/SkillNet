import { useEffect, useRef, useState } from 'react'

/**
 * Fetch a credentialed binary asset into a blob object-URL.
 *
 * A plain `<audio src>` / `<img src>` cannot send the auth cookie the API needs, so the
 * bytes are fetched credentialed and object-URL'd, exactly like the course-surface
 * `PodcastPlayer`/`Infographic` do. The URL is revoked on unmount and on every path
 * change, so no blob leaks.
 *
 * Two asset families ride on this, and they are deliberately different routes because
 * they are different things: a **MediaArtifact** is something SkillNet generated
 * (`/media/artifacts/{id}/asset`), a **SourceImage** is the customer's own picture taken
 * out of their own document (`/documents/{document_id}/images/{image_id}`). Same fetch,
 * same degradation, separate lifetimes.
 */
export interface ArtifactAssetState {
  url: string | null
  loading: boolean
  error: boolean
}

const BASE = '/api/v1'

export function useCredentialedAsset(path: string | null): ArtifactAssetState {
  const [state, setState] = useState<ArtifactAssetState>({
    url: null,
    loading: true,
    error: false,
  })
  const urlRef = useRef<string | null>(null)

  useEffect(() => {
    if (!path) {
      setState({ url: null, loading: false, error: true })
      return
    }
    let cancelled = false
    setState({ url: null, loading: true, error: false })
    ;(async () => {
      try {
        const res = await fetch(path, { credentials: 'include' })
        if (!res.ok) throw new Error('asset fetch failed')
        const url = URL.createObjectURL(await res.blob())
        if (cancelled) {
          URL.revokeObjectURL(url)
          return
        }
        urlRef.current = url
        setState({ url, loading: false, error: false })
      } catch {
        if (!cancelled) setState({ url: null, loading: false, error: true })
      }
    })()
    return () => {
      cancelled = true
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current)
        urlRef.current = null
      }
    }
  }, [path])

  return state
}

/**
 * A generated `MediaArtifact`'s rendered bytes. Shared by the two broker-injected,
 * in-lesson media blocks (`PodcastPlayerBlock`, `InfographicImageBlock`): both only
 * receive an `artifact_id`, and both only need the asset itself — the grounded
 * `spec_json` lives on the course-surface viewers, not here.
 */
export function useArtifactAsset(artifactId: string | undefined): ArtifactAssetState {
  return useCredentialedAsset(
    artifactId ? `${BASE}/media/artifacts/${encodeURIComponent(artifactId)}/asset` : null,
  )
}

/**
 * One image extracted from a customer's own source document (`SourceImageBlock`).
 *
 * The route is document-scoped — an image is only reachable through the document that
 * owns it — so both ids are needed and a missing one degrades to the error state rather
 * than to a request that could not possibly succeed.
 */
export function useSourceImageAsset(
  documentId: string | undefined,
  imageId: string | undefined,
): ArtifactAssetState {
  const path =
    documentId && imageId
      ? `${BASE}/documents/${encodeURIComponent(documentId)}/images/${encodeURIComponent(imageId)}`
      : null
  return useCredentialedAsset(path)
}
