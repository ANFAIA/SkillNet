import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useIntl } from 'react-intl'
import { motion } from 'framer-motion'
import { INLINE_SURFACE, BLOCK_TITLE, BLOCK_EYEBROW } from './blocks/rhythm'

/**
 * Course-level Audio Overview / Podcast player (NotebookLM imitation, roadmap §2a).
 *
 * Plays the generated mp3 from the media asset route and renders the feature every
 * open-source NotebookLM replica skipped: a **parallel citations panel**. The spoken audio
 * carries no citations; provenance lives here instead. Each transcript turn shows the
 * ``citation_ids`` it was grounded on as clickable chips, and the Sources panel lists what
 * each id resolves to (document > section, page). Selecting a source highlights the turns
 * that lean on it; selecting a turn's chip highlights the source — the click-to-passage
 * affordance, wired to ``onJumpToCitation`` when the host surface can scroll to the passage,
 * and otherwise just cross-highlighting within the player.
 *
 * It is additive and self-contained: fed the ``spec_json`` shape the backend persists
 * (``turns`` + ``citations``) and an ``artifactId`` for the audio, so it drops onto the
 * experimental course surface without touching the existing lesson blocks.
 */

export interface PodcastCitation {
  citation_id: string
  document: string
  section?: string | null
  page?: number | null
  document_id?: string | null
}

export interface PodcastTurn {
  speaker: 'A' | 'B'
  text: string
  citation_ids: string[]
}

export interface PodcastPlayerProps {
  /** MediaArtifact id — audio is fetched from `/media/artifacts/{id}/asset`. */
  artifactId: string
  turns: PodcastTurn[]
  citations?: PodcastCitation[]
  format?: string
  /** Display names for the two host labels. Defaults to Lucía / Marcos. */
  hostNames?: { A: string; B: string }
  /** Called when a citation is activated, so the host can scroll to the passage. */
  onJumpToCitation?: (citationId: string) => void
}

const BASE = '/api/v1'

const SPEAKER_STYLES: Record<'A' | 'B', string> = {
  A: 'bg-primary/10 text-primary',
  B: 'bg-accent/10 text-accent',
}

export function PodcastPlayer({
  artifactId,
  turns,
  citations = [],
  format,
  hostNames = { A: 'Lucía', B: 'Marcos' },
  onJumpToCitation,
}: PodcastPlayerProps) {
  const intl = useIntl()

  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeCitation, setActiveCitation] = useState<string | null>(null)

  const urlRef = useRef<string | null>(null)

  // Fetch the mp3 through the credentialed asset route into a blob URL. A plain
  // <audio src> cannot send the auth cookie the API needs, so we fetch then object-URL it.
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    ;(async () => {
      try {
        const res = await fetch(`${BASE}/media/artifacts/${artifactId}/asset`, {
          credentials: 'include',
        })
        if (!res.ok) throw new Error('asset fetch failed')
        const blob = await res.blob()
        if (cancelled) return
        const url = URL.createObjectURL(blob)
        urlRef.current = url
        setAudioUrl(url)
      } catch {
        if (!cancelled) setError(intl.formatMessage({ id: 'podcast.unavailable' }))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
      if (urlRef.current) {
        URL.revokeObjectURL(urlRef.current)
        urlRef.current = null
      }
    }
  }, [artifactId, intl])

  // Only the citations actually referenced by a turn, in bundle order.
  const usedCitations = useMemo(() => {
    const referenced = new Set(turns.flatMap((t) => t.citation_ids))
    const byId = new Map(citations.map((c) => [c.citation_id, c]))
    const ordered = citations.filter((c) => referenced.has(c.citation_id))
    // Include any referenced id we have no metadata for, so a chip is never orphaned.
    for (const id of referenced) {
      if (!byId.has(id)) ordered.push({ citation_id: id, document: id })
    }
    return ordered
  }, [turns, citations])

  const handleCitation = useCallback(
    (id: string) => {
      setActiveCitation((prev) => (prev === id ? null : id))
      onJumpToCitation?.(id)
    },
    [onJumpToCitation],
  )

  const citationLabel = useCallback(
    (c: PodcastCitation) => {
      const parts = [c.document]
      if (c.section) parts.push(c.section)
      let label = parts.join(' › ')
      if (c.page != null) {
        label += ` · ${intl.formatMessage({ id: 'podcast.page' }, { page: c.page })}`
      }
      return label
    },
    [intl],
  )

  const formatLabel = format
    ? intl.formatMessage({ id: `podcast.format.${format}`, defaultMessage: format })
    : null

  return (
    <div data-no-explain="" className={`${INLINE_SURFACE} bg-bg-subtle`}>
      {/* Header + audio element */}
      <div className="mb-4">
        <div className="flex items-center justify-between gap-3 mb-3">
          <h3 className={BLOCK_TITLE + ' mb-0'}>
            {intl.formatMessage({ id: 'podcast.title' })}
          </h3>
          {formatLabel && (
            <span className="text-xs font-medium text-text-muted rounded-full bg-bg px-2.5 py-1">
              {formatLabel}
            </span>
          )}
        </div>

        {loading && (
          <p className="text-sm text-text-muted">
            {intl.formatMessage({ id: 'podcast.loading' })}
          </p>
        )}
        {error && (
          <p className="text-sm text-danger" role="alert">
            {error}
          </p>
        )}
        {audioUrl && !error && (
          // Native controls: robust seeking/scrubbing with no custom timeline to maintain.
          <audio className="w-full" controls src={audioUrl}>
            <track kind="captions" />
          </audio>
        )}
      </div>

      {/* Parallel layout: transcript | sources */}
      <div className="grid gap-4 md:grid-cols-[1fr_minmax(0,15rem)]">
        {/* Transcript */}
        <div className="min-w-0">
          <p className={BLOCK_EYEBROW + ' text-text-muted'}>
            {intl.formatMessage({ id: 'podcast.transcript' })}
          </p>
          <ol className="space-y-3">
            {turns.map((turn, i) => {
              const dimmed =
                activeCitation != null && !turn.citation_ids.includes(activeCitation)
              return (
                <li
                  key={i}
                  className={`flex gap-2.5 transition-opacity duration-150 ${
                    dimmed ? 'opacity-40' : 'opacity-100'
                  }`}
                >
                  <span
                    className={`shrink-0 h-6 w-6 rounded-full grid place-items-center text-xs font-semibold ${SPEAKER_STYLES[turn.speaker]}`}
                    aria-hidden="true"
                  >
                    {(hostNames[turn.speaker] ?? turn.speaker).charAt(0)}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm leading-relaxed text-text">{turn.text}</p>
                    {turn.citation_ids.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {turn.citation_ids.map((id) => (
                          <button
                            key={id}
                            type="button"
                            onClick={() => handleCitation(id)}
                            className={`text-[11px] font-medium rounded px-1.5 py-0.5 cursor-pointer transition-colors ${
                              activeCitation === id
                                ? 'bg-primary text-white'
                                : 'bg-primary/10 text-primary hover:bg-primary/20'
                            }`}
                          >
                            {id}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </li>
              )
            })}
          </ol>
        </div>

        {/* Sources panel */}
        <aside className="min-w-0 md:border-l md:border-border md:pl-4">
          <p className={BLOCK_EYEBROW + ' text-text-muted'}>
            {intl.formatMessage({ id: 'podcast.sources' })}
          </p>
          {usedCitations.length === 0 ? (
            <p className="text-xs text-text-muted">
              {intl.formatMessage({ id: 'podcast.noSources' })}
            </p>
          ) : (
            <ul className="space-y-2">
              {usedCitations.map((c) => (
                <li key={c.citation_id}>
                  <motion.button
                    type="button"
                    onClick={() => handleCitation(c.citation_id)}
                    whileHover={{ scale: 1.01 }}
                    whileTap={{ scale: 0.99 }}
                    className={`w-full text-left rounded-lg border p-2 cursor-pointer transition-colors ${
                      activeCitation === c.citation_id
                        ? 'border-primary bg-primary/5'
                        : 'border-border bg-bg hover:border-primary/40'
                    }`}
                  >
                    <span className="block text-[11px] font-semibold text-primary">
                      {c.citation_id}
                    </span>
                    <span className="block text-xs text-text leading-snug">
                      {citationLabel(c)}
                    </span>
                  </motion.button>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </div>
  )
}
