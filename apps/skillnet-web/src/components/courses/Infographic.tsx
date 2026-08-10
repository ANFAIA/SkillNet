import { useCallback, useMemo, useState } from 'react'
import { useIntl } from 'react-intl'
import { motion } from 'framer-motion'
import { INLINE_SURFACE, BLOCK_TITLE, BLOCK_EYEBROW } from './blocks/rhythm'

/**
 * Infographic viewer (NotebookLM imitation, roadmap §2d).
 *
 * Renders the grounded content spec as a single stylized HTML/SVG sheet — a title, an
 * optional subtitle, and a grid of stat/section cards. The **key rule of §2d**: the facts
 * and numbers are structured data (`stat`, `one_line`) and are **drawn by us as crisp
 * text**, never baked into a generated image. Any decorative background would be art only.
 * Text comes from enumerated fields; nothing is injected as raw HTML.
 *
 * Theme-aware (design tokens, so light/dark both work) and responsive — it reads like a
 * print-ready sheet. Carries the same **parallel citations panel** as the podcast/slides:
 * each section keeps its `citation_ids` as chips, and the Sources aside resolves each id.
 *
 * Additive and self-contained: fed the `spec_json` shape the backend persists (`title`,
 * `sections`, `citations`).
 */

export interface InfographicCitation {
  citation_id: string
  document: string
  section?: string | null
  page?: number | null
  document_id?: string | null
}

export interface InfographicSectionSpec {
  heading: string
  stat?: string | null
  one_line: string
  citation_ids: string[]
}

export interface InfographicProps {
  title: string
  subtitle?: string | null
  sections: InfographicSectionSpec[]
  citations?: InfographicCitation[]
  orientation?: 'portrait' | 'landscape'
  /** Called when a citation is activated, so the host can scroll to the passage. */
  onJumpToCitation?: (citationId: string) => void
}

export function Infographic({
  title,
  subtitle,
  sections,
  citations = [],
  orientation = 'portrait',
  onJumpToCitation,
}: InfographicProps) {
  const intl = useIntl()
  const [activeCitation, setActiveCitation] = useState<string | null>(null)

  const usedCitations = useMemo(() => {
    const referenced = new Set(sections.flatMap((s) => s.citation_ids))
    const byId = new Map(citations.map((c) => [c.citation_id, c]))
    const ordered = citations.filter((c) => referenced.has(c.citation_id))
    for (const id of referenced) {
      if (!byId.has(id)) ordered.push({ citation_id: id, document: id })
    }
    return ordered
  }, [sections, citations])

  const handleCitation = useCallback(
    (id: string) => {
      setActiveCitation((prev) => (prev === id ? null : id))
      onJumpToCitation?.(id)
    },
    [onJumpToCitation],
  )

  const citationLabel = useCallback(
    (c: InfographicCitation) => {
      const parts = [c.document]
      if (c.section) parts.push(c.section)
      let label = parts.join(' › ')
      if (c.page != null) {
        label += ` · ${intl.formatMessage({ id: 'infographic.page' }, { page: c.page })}`
      }
      return label
    },
    [intl],
  )

  // Portrait -> a single narrow column; landscape -> a two-up grid. Both responsive.
  const gridCols =
    orientation === 'landscape'
      ? 'sm:grid-cols-2 lg:grid-cols-3'
      : 'sm:grid-cols-2'

  return (
    <div data-no-explain="" className={`${INLINE_SURFACE} bg-bg-subtle`}>
      <div className="flex items-center justify-between gap-3 mb-3">
        <h3 className={BLOCK_TITLE + ' mb-0'}>
          {intl.formatMessage({ id: 'infographic.title' })}
        </h3>
      </div>

      <div className="grid gap-4 md:grid-cols-[1fr_minmax(0,15rem)]">
        {/* The sheet */}
        <div className="min-w-0">
          <section
            className="rounded-xl border border-border bg-bg p-6"
            aria-label={title}
          >
            {/* Sheet header */}
            <header className="text-center mb-6">
              <h4 className="text-2xl font-bold text-text leading-tight">{title}</h4>
              {subtitle && (
                <p className="text-sm text-text-muted mt-1.5">{subtitle}</p>
              )}
              <div
                className="mx-auto mt-3 h-1 w-16 rounded-full bg-primary"
                aria-hidden="true"
              />
            </header>

            {/* Stat / section grid */}
            <div className={`grid gap-4 ${gridCols}`}>
              {sections.map((section, i) => {
                const dimmed =
                  activeCitation != null &&
                  !section.citation_ids.includes(activeCitation)
                return (
                  <motion.div
                    key={i}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: dimmed ? 0.4 : 1, y: 0 }}
                    transition={{ duration: 0.2, delay: Math.min(i * 0.04, 0.3) }}
                    className="rounded-lg border border-border bg-bg-subtle p-4 flex flex-col"
                  >
                    {section.stat && (
                      <span className="text-3xl font-bold text-primary leading-none mb-1.5">
                        {section.stat}
                      </span>
                    )}
                    <span className="text-sm font-semibold text-text">
                      {section.heading}
                    </span>
                    <span className="text-xs text-text-muted leading-snug mt-1">
                      {section.one_line}
                    </span>
                    {section.citation_ids.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {section.citation_ids.map((id) => (
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
                  </motion.div>
                )
              })}
            </div>
          </section>
        </div>

        {/* Sources panel */}
        <aside className="min-w-0 md:border-l md:border-border md:pl-4">
          <p className={BLOCK_EYEBROW + ' text-text-muted'}>
            {intl.formatMessage({ id: 'infographic.sources' })}
          </p>
          {usedCitations.length === 0 ? (
            <p className="text-xs text-text-muted">
              {intl.formatMessage({ id: 'infographic.noSources' })}
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
