import { useMemo } from 'react'
import { useIntl } from 'react-intl'
import type { NodeKnowledgePack } from '../../types'

const STATUS_KEY = {
  pending: 'schema.packPending',
  ready: 'schema.packReady',
  review_required: 'schema.packReviewRequired',
  stale: 'schema.packStale',
  failed: 'schema.packFailed',
} as const

function statusClass(status: NodeKnowledgePack['status']) {
  if (status === 'ready') return 'text-success'
  if (status === 'review_required' || status === 'failed') return 'text-danger'
  return 'text-text-muted'
}

/** An atom opens with a `###` heading that carries its id and kind — never prose. */
const ATOM_HEADING = /^###\s/
/** Provenance lines the emitter appends under an atom. Not sentences. */
const PROVENANCE = /^(Fuentes|Detalles):/

/**
 * The atoms of a pack, as the sentences a person can read.
 *
 * `pack.markdown` is the server's own review projection of the pack
 * (`knowledge_pack/markdown.py`) and the only place the API exposes the atoms at all:
 * `NodeKnowledgePack` carries counts, hashes and that Markdown, never the atoms
 * themselves. So the sentences have to be read back out of the Markdown here.
 *
 * Per atom the emitter writes a `###` heading holding the atom id and its kind, a blank
 * line, the text on a single line (it collapses newlines itself), a blank line, and then
 * `Fuentes:` / `Detalles:`. Only that one text line is meant for a person; the heading is
 * an internal identifier and the rest is provenance. So this keeps the first body line of
 * every `###` block and drops everything else — the frontmatter, the `##` section
 * headings, and the sections that hold no atoms at all (evidence, generable slots,
 * pending data, sources), which are bullet lists of ids rather than prose.
 *
 * Deliberately structural rather than keyed on the section titles: the emitter's headings
 * are Spanish server-side strings, and matching them here would make a reworded heading
 * silently empty this list.
 */
function packAtoms(markdown: string): string[] {
  const atoms: string[] = []
  let inAtom = false
  for (const raw of markdown.split('\n')) {
    const line = raw.trim()
    if (ATOM_HEADING.test(line)) {
      inAtom = true
      continue
    }
    if (!inAtom || !line) continue
    inAtom = false
    // An atom with no text would otherwise hand its provenance line to the reader as if
    // it were the sentence, and a `#` here means the block ended without one.
    if (line.startsWith('#') || PROVENANCE.test(line)) continue
    atoms.push(line)
  }
  return atoms
}

export function NodeKnowledgePreparation({
  pack,
  loading,
}: {
  pack: NodeKnowledgePack | undefined
  loading: boolean
}) {
  const intl = useIntl()
  const preparing = loading || !pack || pack.status === 'pending' || pack.status === 'stale'
  const atoms = useMemo(() => packAtoms(pack?.markdown ?? ''), [pack?.markdown])

  return (
    <div className="px-2 py-2 border-t border-border mt-2">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="font-medium text-text">
          {intl.formatMessage({ id: 'schema.packTitle' })}
        </span>
        <span
          role="status"
          className={preparing ? 'text-text-muted' : statusClass(pack.status)}
        >
          {preparing
            ? intl.formatMessage({ id: 'schema.packPending' })
            : intl.formatMessage({ id: STATUS_KEY[pack.status] })}
        </span>
      </div>

      {preparing && (
        <p className="text-xs text-text-muted mt-1">
          {intl.formatMessage({ id: 'schema.packPreparingDesc' })}
        </p>
      )}

      {pack?.status === 'ready' && (
        <p className="text-xs text-text-muted mt-1">
          {intl.formatMessage({ id: 'schema.packReadyDesc' })}
        </p>
      )}

      {pack?.status === 'review_required' && (
        <div className="mt-1 text-xs text-text-secondary">
          <p>{intl.formatMessage({ id: 'schema.packReviewDesc' })}</p>
          {pack.blocking_gaps.length > 0 && (
            <ul className="list-disc pl-4 mt-1 text-danger">
              {pack.blocking_gaps.map((gap) => <li key={gap}>{gap}</li>)}
            </ul>
          )}
        </div>
      )}

      {pack?.status === 'failed' && (
        <p role="alert" className="text-xs text-danger mt-1">
          {intl.formatMessage({ id: 'schema.packFailedDesc' })}
        </p>
      )}

      {/* What the generator understood about this node, which is what explains why the
          lesson came out the way it did. Sentences only: this used to dump `pack.markdown`
          verbatim into a `<pre>`, machine headings and atom ids included, which is server
          scaffolding put in front of a person. */}
      {(pack?.status === 'ready' || pack?.status === 'review_required') && atoms.length > 0 && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-text-secondary hover:text-text">
            {intl.formatMessage({ id: 'schema.packSource' })}
          </summary>
          <ul className="mt-2 list-disc space-y-1 rounded-md border border-border bg-bg-muted py-3 pl-7 pr-3 text-xs text-text">
            {/* Keyed by position: the list is re-derived whole from one string, never
                reordered or patched, and two atoms can carry the same sentence. */}
            {atoms.map((atom, index) => <li key={index}>{atom}</li>)}
          </ul>
        </details>
      )}
    </div>
  )
}
