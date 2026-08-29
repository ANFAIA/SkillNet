import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useIntl } from 'react-intl'
import { motion } from 'framer-motion'
import { INLINE_SURFACE, BLOCK_TITLE, BLOCK_EYEBROW } from './blocks/rhythm'
import { SourcesDisclosure } from './SourcesDisclosure'
import { SlideCanvas, type SlideCanvasSpec } from './SlideCanvas'
import type { SlideCitation } from './SlideDeck'

/**
 * Video Overview player (NotebookLM imitation, roadmap §2b).
 *
 * The Video Overview is **narrated slides shipped as HTML**, never a real video model
 * (§2b + the §3 trap note). This player is the sequencing half the backend deliberately
 * left to the frontend: it renders the current slide with the exact `blocks/*.tsx`
 * components the lesson surface and the SlideDeck already use, plays that slide's narration
 * clip, and on `ended` **auto-advances** to the next slide — a hands-off slideshow with a
 * single voice over stills, and no ffmpeg anywhere.
 *
 * Controls: play/pause, manual prev/next, and a segmented scrubber across the slides (click
 * a segment to jump). Under the stage sits the **captions line** — the current slide's
 * narration text with its citation chips — and a Sources aside listing what each cited id
 * resolves to, the parallel-citations affordance every open-source NotebookLM replica
 * skipped.
 *
 * Additive and self-contained: fed the `spec_json` shape the backend persists (`slides`
 * with `narration` + `audio_ref` + `narration_citation_ids`, plus `citations`) and an
 * `artifactId`. Each clip is fetched through the credentialed per-slide asset sub-route into
 * a blob URL. Text is rendered by us from structured fields — nothing is injected as raw
 * HTML, honouring the kit's safety discipline.
 */

export interface VideoSlideSpec extends SlideCanvasSpec {
  citation_ids: string[]
  narration: string
  narration_citation_ids: string[]
  audio_ref: string
  audio_ext?: string
  /** Content hash of this slide's generated illustration, served as a sub-asset. */
  image_ref?: string
  image_ext?: string
}

export interface VideoOverviewProps {
  /** MediaArtifact id — each clip is fetched from `/media/artifacts/{id}/asset/{ref}`. */
  artifactId: string
  slides: VideoSlideSpec[]
  citations?: SlideCitation[]
  theme?: string
  title?: string
  /** Called when a citation is activated, so the host can scroll to the passage. */
  onJumpToCitation?: (citationId: string) => void
}

const BASE = '/api/v1'

export function VideoOverview({
  artifactId,
  slides,
  citations = [],
  theme,
  title,
  onJumpToCitation,
}: VideoOverviewProps) {
  const intl = useIntl()

  const [index, setIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [activeCitation, setActiveCitation] = useState<string | null>(null)
  // ref -> blob URL for every slide clip, filled once on mount.
  const [clipUrls, setClipUrls] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const urlsRef = useRef<string[]>([])

  const total = slides.length
  const clamp = useCallback(
    (n: number) => Math.max(0, Math.min(total - 1, n)),
    [total],
  )

  // Fetch every slide asset through the credentialed sub-asset route into blob URLs. A plain
  // <audio>/<img src> cannot send the auth cookie the API needs, so we fetch then object-URL
  // each. Audio clips are required (a failure surfaces as an error); the per-slide
  // illustrations are best-effort (a missing one just falls back to the kit blocks).
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    const audioRefs = Array.from(new Set(slides.map((s) => s.audio_ref).filter(Boolean)))
    const imageRefs = Array.from(
      new Set(slides.map((s) => s.image_ref).filter((r): r is string => !!r)),
    )
    ;(async () => {
      const map: Record<string, string> = {}
      const fetchInto = async (ref: string) => {
        const res = await fetch(
          `${BASE}/media/artifacts/${artifactId}/asset/${ref}`,
          { credentials: 'include' },
        )
        if (!res.ok) throw new Error('asset fetch failed')
        const url = URL.createObjectURL(await res.blob())
        urlsRef.current.push(url)
        map[ref] = url
      }
      try {
        await Promise.all(audioRefs.map(fetchInto))
        // Illustrations are optional: never let one sink the player.
        await Promise.all(
          imageRefs.map((ref) => fetchInto(ref).catch(() => undefined)),
        )
        if (!cancelled) setClipUrls(map)
      } catch {
        if (!cancelled)
          setError(
            intl.formatMessage({
              id: 'video.narrationUnavailableHint',
              defaultMessage:
                'La narración no está disponible ahora. Puedes leer las diapositivas y sus fuentes.',
            }),
          )
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
      for (const url of urlsRef.current) URL.revokeObjectURL(url)
      urlsRef.current = []
    }
  }, [artifactId, slides, intl])

  const current = slides[clamp(index)]
  const currentUrl = current ? clipUrls[current.audio_ref] : undefined
  const currentImageUrl =
    current && current.image_ref ? clipUrls[current.image_ref] : undefined

  // Drive the <audio> element from the playing/index state: when playing, (re)start the
  // current clip; when paused, hold. The element is keyed by index below so switching
  // slides mounts a fresh clip we then play.
  useEffect(() => {
    const el = audioRef.current
    if (!el) return
    if (playing && currentUrl) {
      void el.play().catch(() => setPlaying(false))
    } else {
      el.pause()
    }
  }, [playing, currentUrl, index])

  useEffect(() => {
    setActiveCitation(null)
  }, [index])

  const onEnded = useCallback(() => {
    // Auto-advance: the whole point of a "video". Stop at the last slide.
    if (index < total - 1) {
      setIndex((i) => clamp(i + 1))
    } else {
      setPlaying(false)
    }
  }, [index, total, clamp])

  const togglePlay = useCallback(() => {
    if (error) return
    // Replaying from the end restarts at the first slide.
    if (!playing && index === total - 1) {
      const el = audioRef.current
      if (el && el.ended) setIndex(0)
    }
    setPlaying((p) => !p)
  }, [error, playing, index, total])

  const goTo = useCallback((n: number) => setIndex(clamp(n)), [clamp])
  const prev = useCallback(() => setIndex((i) => clamp(i - 1)), [clamp])
  const next = useCallback(() => setIndex((i) => clamp(i + 1)), [clamp])

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowRight') {
        e.preventDefault()
        next()
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault()
        prev()
      }
    },
    [next, prev],
  )

  // Every citation any slide's narration leans on, in bundle order, for a stable panel.
  const usedCitations = useMemo(() => {
    const referenced = new Set(
      slides.flatMap((s) => [...s.narration_citation_ids, ...s.citation_ids]),
    )
    const byId = new Map(citations.map((c) => [c.citation_id, c]))
    const ordered = citations.filter((c) => referenced.has(c.citation_id))
    for (const id of referenced) {
      if (!byId.has(id)) ordered.push({ citation_id: id, document: id })
    }
    return ordered
  }, [slides, citations])

  const handleCitation = useCallback(
    (id: string) => {
      setActiveCitation((p) => (p === id ? null : id))
      onJumpToCitation?.(id)
    },
    [onJumpToCitation],
  )

  const citationLabel = useCallback(
    (c: SlideCitation) => {
      const parts = [c.document]
      if (c.section) parts.push(c.section)
      let label = parts.join(' › ')
      if (c.page != null) {
        label += ` · ${intl.formatMessage({ id: 'video.page' }, { page: c.page })}`
      }
      return label
    },
    [intl],
  )

  if (!current) {
    return (
      <div className={`${INLINE_SURFACE} bg-bg-subtle`}>
        <p className="text-sm text-text-muted">
          {intl.formatMessage({ id: 'video.empty' })}
        </p>
      </div>
    )
  }

  const themeLabel = theme && theme !== 'default' ? theme : null
  const captionCites = current.narration_citation_ids

  return (
    <div
      data-no-explain=""
      className={`${INLINE_SURFACE} bg-bg-subtle`}
      onKeyDown={onKeyDown}
      tabIndex={0}
      role="group"
      aria-roledescription={title ?? intl.formatMessage({ id: 'video.title' })}
    >
      <div className="flex items-center justify-between gap-3 mb-3">
        <h3 className={BLOCK_TITLE + ' mb-0'}>
          {title ?? intl.formatMessage({ id: 'video.title' })}
        </h3>
        <div className="flex items-center gap-2">
          {themeLabel && (
            <span className="text-xs font-medium text-text-muted rounded-full bg-bg px-2.5 py-1">
              {themeLabel}
            </span>
          )}
          <span className="text-xs font-medium text-text-muted rounded-full bg-bg px-2.5 py-1">
            {intl.formatMessage(
              { id: 'video.counter' },
              { current: index + 1, total },
            )}
          </span>
        </div>
      </div>

      <div>
        <div className="min-w-0">
          {/* The stage: the current slide */}
          <motion.div
            key={index}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.15 }}
          >
            <SlideCanvas slide={current} imageUrl={currentImageUrl} />
          </motion.div>

          {/* Hidden audio element for the current clip, keyed so each slide remounts. */}
          {currentUrl && (
            <audio
              key={current.audio_ref}
              ref={audioRef}
              src={currentUrl}
              onEnded={onEnded}
              className="hidden"
            >
              <track kind="captions" />
            </audio>
          )}

          {/* Captions: the spoken narration + its citation chips */}
          <div className="mt-3 rounded-lg border border-border bg-bg px-3 py-2">
            <p className={BLOCK_EYEBROW + ' text-text-muted'}>
              {intl.formatMessage({ id: 'video.captions' })}
            </p>
            <p className="text-sm leading-relaxed text-text">{current.narration}</p>
            {captionCites.length > 0 && (
              <div className="mt-1.5 flex flex-wrap items-center gap-1">
                {captionCites.map((id) => (
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

          {loading && (
            <p className="mt-2 text-sm text-text-muted">
              {intl.formatMessage({ id: 'video.loading' })}
            </p>
          )}
          {/*
            Muted, not `text-danger`/`role="alert"`: the narration being unreachable is a
            deployment fault the viewer can neither cause nor fix, and the slides, their
            text and their sources are all still readable here. The transport stays visibly
            disabled below — a dead control that says why, the same shape as
            `CapabilityExplain` — so nothing pretends it can still play.
          */}
          {error && <p className="mt-2 text-sm text-text-muted">{error}</p>}

          {/* Transport: play/pause, scrubber, prev/next */}
          <div className="mt-4 flex items-center gap-3">
            <button
              type="button"
              onClick={togglePlay}
              disabled={!!error}
              aria-label={intl.formatMessage({
                id: playing ? 'video.pause' : 'video.play',
              })}
              className="shrink-0 h-9 w-9 grid place-items-center rounded-full bg-primary text-white cursor-pointer transition-transform hover:scale-105 disabled:opacity-40 disabled:cursor-default"
            >
              {playing ? (
                <svg width="14" height="14" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true">
                  <rect x="2" y="1.5" width="2.6" height="9" rx="0.6" />
                  <rect x="7.4" y="1.5" width="2.6" height="9" rx="0.6" />
                </svg>
              ) : (
                <svg width="14" height="14" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true">
                  <path d="M3 1.8v8.4a.6.6 0 0 0 .92.5l6.5-4.2a.6.6 0 0 0 0-1L3.92 1.3A.6.6 0 0 0 3 1.8Z" />
                </svg>
              )}
            </button>

            {/* Segmented scrubber across slides */}
            <div className="flex flex-1 items-center gap-1" role="group" aria-label={title ?? intl.formatMessage({ id: 'video.title' })}>
              {slides.map((s, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => goTo(i)}
                  aria-label={intl.formatMessage(
                    { id: 'video.goToSlide' },
                    { current: i + 1, total },
                  )}
                  aria-current={i === index}
                  className="group flex-1 py-2 cursor-pointer"
                  title={s.title}
                >
                  <span
                    className={`block h-1.5 rounded-full transition-colors ${
                      i === index
                        ? 'bg-primary'
                        : i < index
                          ? 'bg-primary/40'
                          : 'bg-border group-hover:bg-primary/30'
                    }`}
                  />
                </button>
              ))}
            </div>

            <div className="flex shrink-0 gap-1.5">
              <button
                type="button"
                onClick={prev}
                disabled={index === 0}
                aria-label={intl.formatMessage({ id: 'video.prev' })}
                className="rounded-lg border border-border bg-bg px-2.5 py-1.5 text-sm text-text cursor-pointer transition-colors hover:border-primary/40 disabled:opacity-40 disabled:cursor-default"
              >
                ‹
              </button>
              <button
                type="button"
                onClick={next}
                disabled={index === total - 1}
                aria-label={intl.formatMessage({ id: 'video.next' })}
                className="rounded-lg border border-border bg-bg px-2.5 py-1.5 text-sm text-text cursor-pointer transition-colors hover:border-primary/40 disabled:opacity-40 disabled:cursor-default"
              >
                ›
              </button>
            </div>
          </div>
        </div>

        {/* Sources — collapsed by default */}
        <SourcesDisclosure
          label={intl.formatMessage({ id: 'video.sources' })}
          count={usedCitations.length}
        >
          {usedCitations.length === 0 ? (
            <p className="text-xs text-text-muted">
              {intl.formatMessage({ id: 'video.noSources' })}
            </p>
          ) : (
            <ul className="space-y-2">
              {usedCitations.map((c) => {
                const onThisSlide = captionCites.includes(c.citation_id)
                return (
                  <li key={c.citation_id}>
                    <motion.button
                      type="button"
                      onClick={() => handleCitation(c.citation_id)}
                      whileHover={{ scale: 1.01 }}
                      whileTap={{ scale: 0.99 }}
                      className={`w-full text-left rounded-lg border p-2 cursor-pointer transition-colors ${
                        activeCitation === c.citation_id
                          ? 'border-primary bg-primary/5'
                          : onThisSlide
                            ? 'border-primary/40 bg-bg'
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
                )
              })}
            </ul>
          )}
        </SourcesDisclosure>
      </div>
    </div>
  )
}
