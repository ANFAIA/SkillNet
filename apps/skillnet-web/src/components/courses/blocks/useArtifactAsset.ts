import { useEffect, useRef, useState } from 'react'

/**
 * Fetch a MediaArtifact's rendered bytes (`/media/artifacts/{id}/asset`) into a blob
 * object-URL. A plain `<audio src>` / `<img src>` cannot send the auth cookie the API
 * needs, so the bytes are fetched credentialed and object-URL'd, exactly like the
 * course-surface `PodcastPlayer`/`Infographic` do. The URL is revoked on unmount and on
 * every id change, so no blob leaks.
 *
 * Shared by the two broker-injected, in-lesson media blocks (`PodcastPlayerBlock`,
 * `InfographicImageBlock`): both only receive an `artifact_id`, and both only need the
 * asset itself — the grounded `spec_json` lives on the course-surface viewers, not here.
 */
export interface ArtifactAssetState {
  url: string | null
  loading: boolean
  error: boolean
}

const BASE = '/api/v1'

export function useArtifactAsset(artifactId: string | undefined): ArtifactAssetState {
  const [state, setState] = useState<ArtifactAssetState>({
    url: null,
    loading: true,
    error: false,
  })
  const urlRef = useRef<string | null>(null)

  useEffect(() => {
    if (!artifactId) {
      setState({ url: null, loading: false, error: true })
      return
    }
    let cancelled = false
    setState({ url: null, loading: true, error: false })
    ;(async () => {
      try {
        const res = await fetch(`${BASE}/media/artifacts/${artifactId}/asset`, {
          credentials: 'include',
        })
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
  }, [artifactId])

  return state
}
