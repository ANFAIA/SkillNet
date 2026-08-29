import { useCallback, useEffect, useMemo, useState } from 'react'
import { useIntl } from 'react-intl'
import { motion } from 'framer-motion'
import { INLINE_SURFACE, BLOCK_TITLE } from './blocks/rhythm'
import {
  SlideCanvas,
  type SlideCanvasSpec,
} from './SlideCanvas'
import { SourcesDisclosure } from './SourcesDisclosure'

/**
 * Slide Deck viewer (NotebookLM imitation, roadmap §2c).
 *
 * Renders a grounded, per-slide-structured deck: each slide is **kit blocks in a slide
 * frame** — the exact `blocks/*.tsx` components the lesson surface already uses — so the
 * deck reuses the frozen kit vocabulary rather than inventing a second one. Keyboard
 * (←/→, Home/End) and prev/next navigation, one idea per slide, and the **parallel
 * citations panel** every open-source NotebookLM replica skipped: each slide keeps its
 * `citation_ids`, shown as footnote chips, and the Sources aside lists what each id
 * resolves to. Selecting a source highlights it; selecting a slide's chip cross-highlights.
 *
 * Additive and self-contained: fed the `spec_json` shape the backend persists (`slides` +
 * `citations`). Text is rendered by us from structured fields — nothing is injected as raw
 * HTML, honouring the kit's safety discipline.
 */

export interface SlideCitation {
  citation_id: string
  document: string
  section?: string | null
  page?: number | null
  document_id?: string | null
}

export interface SlideSpec extends SlideCanvasSpec {
  citation_ids: string[]
  /** Legacy fields retained so previously persisted artifacts still deserialize. */
  image_ref?: string
  image_ext?: string
}

export type { SlideBlockSpec, SlideComposition } from './SlideCanvas'

export interface SlideDeckProps {
  /** MediaArtifact id, retained as part of the stable viewer API. */
  artifactId: string
  slides: SlideSpec[]
  citations?: SlideCitation[]
  theme?: string
  /** Called when a citation is activated, so the host can scroll to the passage. */
  onJumpToCitation?: (citationId: string) => void
}

export function SlideDeck({
  slides,
  citations = [],
  theme,
  onJumpToCitation,
}: SlideDeckProps) {
  const intl = useIntl()
  const [index, setIndex] = useState(0)
  const [activeCitation, setActiveCitation] = useState<string | null>(null)
  const total = slides.length
  const clamp = useCallback(
    (n: number) => Math.max(0, Math.min(total - 1, n)),
    [total],
  )
  const next = useCallback(() => setIndex((i) => clamp(i + 1)), [clamp])
  const prev = useCallback(() => setIndex((i) => clamp(i - 1)), [clamp])

  // Keyboard navigation while the deck (or a child) has focus.
  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowRight') {
        e.preventDefault()
        next()
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault()
        prev()
      } else if (e.key === 'Home') {
        e.preventDefault()
        setIndex(0)
      } else if (e.key === 'End') {
        e.preventDefault()
        setIndex(total - 1)
      }
    },
    [next, prev, total],
  )

  useEffect(() => {
    setActiveCitation(null)
  }, [index])

  const current = slides[clamp(index)]

  // Every citation any slide leans on, in bundle order, so the sources panel is stable.
  const usedCitations = useMemo(() => {
    const referenced = new Set(slides.flatMap((s) => s.citation_ids))
    const byId = new Map(citations.map((c) => [c.citation_id, c]))
    const ordered = citations.filter((c) => referenced.has(c.citation_id))
    for (const id of referenced) {
      if (!byId.has(id)) ordered.push({ citation_id: id, document: id })
    }
    return ordered
  }, [slides, citations])

  const handleCitation = useCallback(
    (id: string) => {
      setActiveCitation((prev) => (prev === id ? null : id))
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
        label += ` · ${intl.formatMessage({ id: 'slides.page' }, { page: c.page })}`
      }
      return label
    },
    [intl],
  )

  if (!current) {
    return (
      <div className={`${INLINE_SURFACE} bg-bg-subtle`}>
        <p className="text-sm text-text-muted">
          {intl.formatMessage({ id: 'slides.empty' })}
        </p>
      </div>
    )
  }

  const themeLabel = theme && theme !== 'default' ? theme : null

  return (
    <div
      data-no-explain=""
      className={`${INLINE_SURFACE} bg-bg-subtle`}
      onKeyDown={onKeyDown}
      tabIndex={0}
      role="group"
      aria-roledescription={intl.formatMessage({ id: 'slides.title' })}
    >
      <div className="flex items-center justify-between gap-3 mb-3">
        <h3 className={BLOCK_TITLE + ' mb-0'}>
          {intl.formatMessage({ id: 'slides.title' })}
        </h3>
        <div className="flex items-center gap-2">
          {themeLabel && (
            <span className="text-xs font-medium text-text-muted rounded-full bg-bg px-2.5 py-1">
              {themeLabel}
            </span>
          )}
          <span className="text-xs font-medium text-text-muted rounded-full bg-bg px-2.5 py-1">
            {intl.formatMessage(
              { id: 'slides.counter' },
              { current: index + 1, total },
            )}
          </span>
        </div>
      </div>

      <div>
        {/* The slide */}
        <div className="min-w-0">
          <motion.div
            key={index}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.15 }}
          >
            <SlideCanvas slide={current} />
          </motion.div>

          {/* Footnote citation chips for the current slide */}
          {current.citation_ids.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-1">
              <span className="text-[11px] text-text-muted mr-1">
                {intl.formatMessage({ id: 'slides.sources' })}:
              </span>
              {current.citation_ids.map((id) => (
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

          {/* Prev / next */}
          <div className="mt-4 flex items-center justify-between">
            <button
              type="button"
              onClick={prev}
              disabled={index === 0}
              className="rounded-lg border border-border bg-bg px-3 py-1.5 text-sm text-text cursor-pointer transition-colors hover:border-primary/40 disabled:opacity-40 disabled:cursor-default"
            >
              {intl.formatMessage({ id: 'slides.prev' })}
            </button>
            <div className="flex gap-1.5" aria-hidden="true">
              {slides.map((_, i) => (
                <span
                  key={i}
                  className={`h-1.5 rounded-full transition-all ${
                    i === index ? 'w-4 bg-primary' : 'w-1.5 bg-border'
                  }`}
                />
              ))}
            </div>
            <button
              type="button"
              onClick={next}
              disabled={index === total - 1}
              className="rounded-lg border border-border bg-bg px-3 py-1.5 text-sm text-text cursor-pointer transition-colors hover:border-primary/40 disabled:opacity-40 disabled:cursor-default"
            >
              {intl.formatMessage({ id: 'slides.next' })}
            </button>
          </div>
        </div>

        {/* Sources — collapsed by default */}
        <SourcesDisclosure
          label={intl.formatMessage({ id: 'slides.sources' })}
          count={usedCitations.length}
        >
          {usedCitations.length === 0 ? (
            <p className="text-xs text-text-muted">
              {intl.formatMessage({ id: 'slides.noSources' })}
            </p>
          ) : (
            <ul className="space-y-2">
              {usedCitations.map((c) => {
                const onThisSlide = current.citation_ids.includes(c.citation_id)
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
