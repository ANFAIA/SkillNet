/**
 * The runtime half of the mandatory profile "sin reactividad", under test.
 *
 * The profile is enforced by **what is not passed** to `<Renderer>`, which is exactly
 * the kind of correctness a test suite does not notice: before this file the only thing
 * protecting it was a comment. The audit calls the missing `toolProvider` "el corte duro
 * y es el que recomiendo para la adopcion" — it is the control that guarantees zero
 * network egress, because there is no `fetch`/`XMLHttpRequest`/`WebSocket`/`sendBeacon`
 * anywhere in either vendor bundle and `toolProvider.callTool` is the only egress the
 * package has.
 *
 * Adding the prop is enough on its own to open it: `Query` self-fires in a `useEffect`
 * as soon as `isStreaming` goes false, with no click and no registered component, and
 * takes an unbounded `refreshInterval` (measured: 4 calls in 3.3 s with
 * `refreshInterval=1`).
 *
 * `assertStaticOnly.test.ts` covers the gate, which is defence in depth. This file
 * covers the switch itself.
 */

import fs from 'node:fs'
import path from 'node:path'

import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

/** Every props object `<Renderer>` was mounted with, in order. */
const mounted: Record<string, unknown>[] = []

vi.mock('@openuidev/react-lang', async () => {
  // Only `Renderer` is replaced: the gate's `createParser` and the kit's
  // `defineComponent` must stay real, or the test would prove nothing about the
  // program that actually reaches the runtime.
  const actual =
    await vi.importActual<typeof import('@openuidev/react-lang')>('@openuidev/react-lang')
  return {
    ...actual,
    Renderer: (props: Record<string, unknown>) => {
      mounted.push(props)
      return null
    },
  }
})

// Imported after the mock so the component under test closes over the spy.
import { UiSpecRenderer } from './UiSpecRenderer'

const PROGRAM = [
  'root = Stack([intro], "md")',
  'intro = TextContent("Las devoluciones se aceptan durante 30 dias naturales.", "lead")',
].join('\n')

/**
 * The three props that switch the reactive layer back on, and one hazard each:
 *
 * - `toolProvider` → `createQueryManager(<this>)` instead of `createQueryManager(null)`:
 *   every `Query` and `Mutation` becomes a real call.
 * - `onAction` → `@OpenUrl` and `@ToAssistant` stop being no-ops. The parser accepts a
 *   `javascript:` URL and an arbitrary assistant message without complaint.
 * - `onStateUpdate` → `@Set` (which writes any state key, with no allowlist) starts
 *   being persisted by the host.
 */
const FORBIDDEN_PROPS = ['toolProvider', 'onAction', 'onStateUpdate'] as const

const COURSES_DIR = path.resolve(__dirname)

function sourceFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) return sourceFiles(full)
    return /\.tsx?$/.test(entry.name) ? [full] : []
  })
}

describe('the props <Renderer> is mounted with', () => {
  it.each(FORBIDDEN_PROPS)('does not carry %s — not even as a key', (name) => {
    mounted.length = 0
    render(<UiSpecRenderer program={PROGRAM} nodeId="node-1" renderId="render-1" />)

    expect(mounted).toHaveLength(1)
    // Absence of the KEY, not `=== undefined`: `toolProvider={undefined}` must fail this
    // too, because a later edit that threads a maybe-provider through is the realistic
    // way this regresses.
    expect(Object.keys(mounted[0])).not.toContain(name)
    expect(name in mounted[0]).toBe(false)
  })

  it('carries only the four props the profile allows', () => {
    mounted.length = 0
    render(<UiSpecRenderer program={PROGRAM} nodeId="node-1" isStreaming />)

    expect(Object.keys(mounted[0]).sort()).toEqual([
      'isStreaming',
      'library',
      'onError',
      'response',
    ])
  })

  it('is mounted with the re-serialized program, never with anything else', () => {
    mounted.length = 0
    render(<UiSpecRenderer program={PROGRAM} nodeId="node-1" />)
    expect(mounted[0].response).toBe(PROGRAM)
  })

  it('is not mounted at all when the gate blocks the program', () => {
    mounted.length = 0
    render(
      <UiSpecRenderer
        program={'$v = 0\nroot = Stack([a], "md")\na = TextContent("v", "body")'}
        nodeId="node-1"
      />,
    )
    expect(mounted).toHaveLength(0)
  })
})

describe('the vendor surface the kit is allowed to import', () => {
  /**
   * Importing one of these is the only way to reach the reactive layer from our side.
   * `useTriggerAction` is the decisive one: it is what a registered component would need
   * to fire a `Mutation` or an `@OpenUrl`, and "no component calls it" is why an
   * `ActionPlan` is *physically* unfirable rather than merely unconfigured.
   */
  const FORBIDDEN_IMPORTS = [
    'useTriggerAction',
    'reactive',
    'markReactive',
    'createQueryManager',
    'createStore',
    'useStateField',
  ]

  const IMPORT_RE = /import\s+(?:type\s+)?\{([^}]*)\}\s*from\s*['"](@openuidev\/[^'"]+)['"]/g

  it('reads the whole courses tree, so the check cannot pass by finding nothing', () => {
    const files = sourceFiles(COURSES_DIR)
    expect(files.length).toBeGreaterThan(10)
    expect(files.some((file) => file.endsWith('library.tsx'))).toBe(true)
  })

  it.each(FORBIDDEN_IMPORTS)('never imports %s from @openuidev', (name) => {
    for (const file of sourceFiles(COURSES_DIR)) {
      const source = fs.readFileSync(file, 'utf8')
      for (const match of source.matchAll(IMPORT_RE)) {
        const imported = match[1].split(',').map((part) => part.trim().split(/\s+as\s+/)[0].trim())
        expect(imported, `${path.basename(file)} imports from ${match[2]}`).not.toContain(name)
      }
    }
  })

  it('mounts <Renderer> from exactly one module, the one asserted above', () => {
    const importers = sourceFiles(COURSES_DIR).filter((file) => {
      if (/\.test\.tsx?$/.test(file)) return false
      const source = fs.readFileSync(file, 'utf8')
      return [...source.matchAll(IMPORT_RE)].some((match) =>
        match[1].split(',').some((part) => part.trim() === 'Renderer'),
      )
    })
    expect(importers.map((file) => path.basename(file))).toEqual(['UiSpecRenderer.tsx'])
  })
})
