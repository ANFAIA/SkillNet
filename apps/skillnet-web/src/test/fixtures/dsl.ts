/**
 * The dialect corpus, read straight from the backend's fixture directory.
 *
 * There is no local copy and no drift-check script any more: the input to the
 * renderer is now the same OpenUI Lang text the backend parser is tested with, so
 * pointing at `apps/skillnet-api/tests/fixtures/dsl/` makes B1's set canonical by
 * construction instead of by a byte-comparison hook (the old
 * `scripts/check-ui-spec-fixtures.mjs`, deleted with the JSON fixtures).
 *
 * A frontend-only checkout has no backend directory; `hasDslCorpus` is false there
 * and the suites that need the corpus skip themselves.
 */

import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))

export const DSL_DIR = join(here, '..', '..', '..', '..', 'skillnet-api', 'tests', 'fixtures', 'dsl')

export const hasDslCorpus = existsSync(DSL_DIR)

function load(): Record<string, string> {
  if (!hasDslCorpus) return {}
  const out: Record<string, string> = {}
  for (const file of readdirSync(DSL_DIR).sort()) {
    if (!file.endsWith('.openui')) continue
    out[file.replace(/\.openui$/, '')] = readFileSync(join(DSL_DIR, file), 'utf8')
  }
  return out
}

/** All 17 fixtures, keyed by file name without the extension. */
export const dslFixtures = load()

const isBroken = (name: string) => name.startsWith('malformed') || name.startsWith('invalid')

/**
 * The eleven programs the backend validator accepts. Between them they exercise
 * nine of the ten frozen components; `Markdown` has no `.openui` fixture because
 * the model cannot emit it (§5.3), so its test builds the fallback program inline.
 *
 * `inline_nested` is the one written in the standard's inline form — sub-components
 * spelled out inside their parent's array instead of referenced by id. Both parsers
 * have to accept it: theirs always did, ours does since 2026-07-27.
 */
export const validPrograms: Record<string, string> = Object.fromEntries(
  Object.entries(dslFixtures).filter(([name]) => !isBroken(name)),
)

/** The six the backend rejects — three of them silently accepted by OpenUI's parser. */
export const brokenPrograms: Record<string, string> = Object.fromEntries(
  Object.entries(dslFixtures).filter(([name]) => isBroken(name)),
)

/** `fallback_seed`: the one program the browser renders that the LLM never writes. */
export const FALLBACK_MARKDOWN_PROGRAM = [
  'root = Stack([semilla], "md")',
  'semilla = Markdown("## Devoluciones\\n\\nSe aceptan durante **30 dias naturales**.")',
].join('\n')
