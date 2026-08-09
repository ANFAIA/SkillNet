/**
 * The drift alarm between this kit and the frozen catalogue of §5.3.
 *
 * `apps/skillnet-api/src/render/openui_catalog.json` is generated from
 * `src/render/kit.py` (the source of truth for the prompt and the validator) by
 * `scripts/generate-openui-prompt.mjs`. If a name, a description, a prop name or —
 * the dangerous one — a **prop ORDER** ever differs between that artefact and the
 * zod schemas here, every generated program is silently reinterpreted: OpenUI maps
 * positional arguments onto props by key order, so swapping two keys swaps two
 * values with no error anywhere.
 *
 * That is the one failure mode of this migration that no other test can see, and
 * the reason it is checked against a file rather than against a copy of the table.
 */

import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

import { skillnetLibrary, skillnetLibrarySchema } from './library'
import {
  BLOOM_LEVELS,
  CALLOUT_TONES,
  CHART_KINDS,
  ITEM_TYPES,
  KIT_COMPONENT_NAMES,
  MAX_COMPONENTS,
  MAX_RENDERED_ELEMENTS,
  STACK_GAPS,
  TEXT_VARIANTS,
  VOICE_STYLES,
} from './schemas'

const here = dirname(fileURLToPath(import.meta.url))
const CATALOG = join(here, '..', '..', '..', '..', '..', 'skillnet-api', 'src', 'render', 'openui_catalog.json')

interface CatalogProp {
  name: string
  kind: string
  choices: string[]
  optional: boolean
}
interface CatalogComponent {
  name: string
  description: string
  signature: string
  props: CatalogProp[]
}
interface Catalog {
  catalog_id: string
  root: string
  /** Names only — the ten the browser can render. */
  render_components: string[]
  /** The nine the model is taught, with descriptions and prop kinds. */
  prompt_components: CatalogComponent[]
  /** `Stack(children:ref[], gap:enum(sm|md|lg))`, one line per component. */
  canonical_catalog: string
}

/** Reads the canonical line of one component: prop names in order, enum members. */
function canonicalProps(component: string): { names: string[]; enums: Record<string, string[]> } {
  const line = (catalog?.canonical_catalog ?? '')
    .split('\n')
    .find((candidate) => candidate.startsWith(`${component}(`))
  if (!line) return { names: [], enums: {} }
  const body = line.slice(component.length + 1, line.lastIndexOf(')'))
  // Split on commas that are not inside an enum(...) group.
  const parts: string[] = []
  let depth = 0
  let current = ''
  for (const char of body) {
    if (char === '(') depth += 1
    if (char === ')') depth -= 1
    if (char === ',' && depth === 0) {
      parts.push(current.trim())
      current = ''
      continue
    }
    current += char
  }
  if (current.trim()) parts.push(current.trim())

  const names: string[] = []
  const enums: Record<string, string[]> = {}
  for (const part of parts) {
    const [name, kind] = part.split(':')
    names.push(name.trim())
    const match = /^enum\((.*)\)$/.exec((kind ?? '').trim())
    if (match) enums[name.trim()] = match[1].split('|')
  }
  return { names, enums }
}

const hasCatalog = existsSync(CATALOG)
const catalog: Catalog | null = hasCatalog
  ? (JSON.parse(readFileSync(CATALOG, 'utf8')) as Catalog)
  : null

/** Prop names in the order lang-core will read them as positional arguments. */
function propOrder(component: string): string[] {
  const def = skillnetLibrarySchema.$defs?.[component]
  return Object.keys((def?.properties ?? {}) as Record<string, unknown>)
}

describe('the kit is the catalogue of §5.3', () => {
  it('registers the ten frozen components under the library root Stack', () => {
    expect(Object.keys(skillnetLibrary.components).sort()).toEqual([...KIT_COMPONENT_NAMES].sort())
    expect(skillnetLibrary.root).toBe('Stack')
    expect(skillnetLibrary.id).toBe('skillnet-ui/1')
  })

  it('puts every prop in the dialect positional order', () => {
    expect(propOrder('Stack')).toEqual(['children', 'gap'])
    expect(propOrder('TextContent')).toEqual(['text', 'variant'])
    expect(propOrder('Card')).toEqual(['title', 'children'])
    expect(propOrder('Callout')).toEqual(['tone', 'text'])
    expect(propOrder('StepSequence')).toEqual(['title', 'steps'])
    expect(propOrder('Table')).toEqual(['headers', 'rows'])
    expect(propOrder('CodeBlock')).toEqual(['language', 'code'])
    expect(propOrder('Chart')).toEqual(['kind', 'title', 'labels', 'values'])
    expect(propOrder('QuizItem')).toEqual([
      'item_id',
      'item_type',
      'bloom_level',
      'question',
      'options',
    ])
    expect(propOrder('SliderExploration')).toEqual([
      'title',
      'variable',
      'min',
      'max',
      'step',
      'formula',
      'description',
    ])
    expect(propOrder('ManipulableGraph')).toEqual([
      'title',
      'xLabel',
      'yLabel',
      'points',
      'functions',
    ])
    expect(propOrder('BeforeAfter')).toEqual([
      'title',
      'beforeLabel',
      'beforeContent',
      'afterLabel',
      'afterContent',
    ])
    expect(propOrder('Markdown')).toEqual(['content'])
    expect(propOrder('DragOrder')).toEqual(['instruction', 'items', 'correctOrder'])
    expect(propOrder('HotspotImage')).toEqual(['imageUrl', 'alt', 'hotspots'])
    expect(propOrder('StepByStepReveal')).toEqual(['title', 'steps'])
    expect(propOrder('AudioExplanation')).toEqual(['text', 'voice'])
    expect(propOrder('PronunciationExercise')).toEqual(['targetText', 'language'])
    expect(propOrder('DiagramBuilder')).toEqual(['title', 'steps'])
    expect(propOrder('Accordion')).toEqual(['children'])
    expect(propOrder('AccordionItem')).toEqual(['trigger', 'children'])
  })

  it('declares every prop required — the kit has no optional props', () => {
    for (const name of KIT_COMPONENT_NAMES) {
      const def = skillnetLibrarySchema.$defs?.[name]
      expect(def?.required?.slice().sort()).toEqual(propOrder(name).slice().sort())
    }
  })
})

describe.skipIf(!hasCatalog)('no drift against the backend catalogue artefact', () => {
  it('agrees on the catalogue id and the root', () => {
    expect(catalog!.catalog_id).toBe(skillnetLibrary.id)
    expect(catalog!.root).toBe(skillnetLibrary.root)
  })

  it('agrees on the ten component names', () => {
    expect(catalog!.render_components).toEqual([...KIT_COMPONENT_NAMES])
  })

  const ENUMS: Record<string, readonly string[]> = {
    gap: STACK_GAPS,
    variant: TEXT_VARIANTS,
    tone: CALLOUT_TONES,
    kind: CHART_KINDS,
    item_type: ITEM_TYPES,
    bloom_level: BLOOM_LEVELS,
    voice: VOICE_STYLES,
  }

  it('lists Markdown as renderable but never in the canonical prompt catalogue', () => {
    expect(catalog!.render_components).toContain('Markdown')
    expect(canonicalProps('Markdown').names).toEqual([])
  })

  it.each([...KIT_COMPONENT_NAMES].filter((name) => name !== 'Markdown'))(
    'agrees on %s: prop names, prop ORDER and enum members',
    (name) => {
      const canonical = canonicalProps(name)
      expect(canonical.names, `${name} missing from canonical_catalog`).not.toEqual([])
      // The load-bearing assertion of this whole file.
      expect(propOrder(name)).toEqual(canonical.names)
      for (const [prop, members] of Object.entries(canonical.enums)) {
        expect(ENUMS[prop], `no enum wired for ${name}.${prop}`).toBeDefined()
        expect([...ENUMS[prop]]).toEqual(members)
      }
    },
  )

  it('agrees on the description of every component the model is taught', () => {
    for (const component of catalog!.prompt_components) {
      expect(skillnetLibrary.components[component.name]?.description).toBe(component.description)
      expect(propOrder(component.name)).toEqual(component.props.map((prop) => prop.name))
    }
  })

  it('keeps Markdown out of what the model is taught to emit', () => {
    const promptNames = catalog!.prompt_components.map((component) => component.name)
    expect(promptNames).not.toContain('Markdown')
    expect(promptNames).toHaveLength(20)
    // …and in what the browser can render, for `fallback_seed`.
    expect(Object.keys(skillnetLibrary.components)).toContain('Markdown')
  })
})

/**
 * The two caps of contract rule 4 are written twice — `src/render/spec.py` (the one that
 * decides what is served) and `schemas.ts` (the fail-closed copy) — and they are not in
 * the generated catalogue, so nothing else notices if they diverge. Divergence is not
 * academic in either direction: a server cap raised above the client's would blank
 * perfectly valid lessons, and a client cap raised above the server's would be a gate
 * that no longer gates.
 */
describe('rule 4 — the caps agree with the validator', () => {
  const SPEC_PY = join(here, '..', '..', '..', '..', '..', 'skillnet-api', 'src', 'render', 'spec.py')
  const source = existsSync(SPEC_PY) ? readFileSync(SPEC_PY, 'utf8') : null

  const constant = (name: string): number | null => {
    const match = source?.match(new RegExp(`^${name} = (\\d[\\d_]*)$`, 'm'))
    return match ? Number(match[1].replaceAll('_', '')) : null
  }

  it.each([
    ['MAX_COMPONENTS', MAX_COMPONENTS],
    ['MAX_RENDERED_NODES', MAX_RENDERED_ELEMENTS],
  ])('%s matches the Python constant', (name, here_) => {
    expect(source, `${SPEC_PY} is not readable`).not.toBeNull()
    expect(constant(name), `${name} not found in spec.py`).not.toBeNull()
    expect(constant(name)).toBe(here_)
  })
})
