/**
 * The static-only gate — the frontend half of the mandatory profile "sin
 * reactividad".
 *
 * Ported from the security audit's `sec-gate3.mjs` (15/15 injection payloads
 * rejected, 0 false positives on the ten valid `.openui` fixtures). The audit's
 * headline finding is why this file exists at all:
 *
 *   **OpenUI's parser rejects nothing.** `Query` and `Mutation` are wired into
 *   `RESERVED_CALLS` inside the parser, not into the component library, so with
 *   zero tools registered `z = Mutation("delete_all_users", {…})` parses with
 *   `meta.errors == []` and shows up clean in `mutationStatements`. `$variables`
 *   auto-declare as `null`. "We did not register it, so the parser flags it" is
 *   FALSE. The gate is ours or there is no gate.
 *
 * It is defence in depth, not the primary control. Four things already stand
 * between a poisoned document and a network call: the backend never persists a
 * program it could not validate; the browser is fed text re-serialized from the
 * validated `UISpec`, never the model's `raw_dsl`; `<Renderer>` gets no
 * `toolProvider`, so `createQueryManager(null)` short-circuits every query and
 * mutation; and no component in the library calls `useTriggerAction()`, so no
 * `ActionPlan` can ever fire. This gate is what notices when one of those four
 * has been bypassed.
 *
 * Deliberately NOT a keyword grep over the program text: measured false positive
 * on legitimate prose ("En SQL una `Query()` se escribe con SELECT", "$300").
 * Structural checks over the `ParseResult` only.
 */

import { createParser, createStreamingParser } from '@openuidev/react-lang'
import type { ParseResult } from '@openuidev/react-lang'

import { MAX_COMPONENTS, MAX_RENDERED_ELEMENTS } from './schemas'
import { skillnetLibrarySchema } from './library'

/**
 * AST node kinds that only exist when a program computes something at render
 * time. A static program's props are literals, arrays of literals and resolved
 * elements — nothing else.
 */
const RUNTIME_KINDS = new Set([
  'StateRef',
  'RuntimeRef',
  'BinOp',
  'UnaryOp',
  'Ternary',
  'Member',
  'Index',
  'Assign',
])

/**
 * Elements in the tree `root` expands to, counting every reference separately, and
 * stopping as soon as the answer is known to exceed `ceiling`.
 *
 * The early exit is the point: the whole hazard is a tree that is expensive to touch,
 * so the check must not be the thing that walks all of it. Work is bounded by
 * `ceiling` pops, each pushing at most one node's worth of props.
 */
function countElements(root: unknown, ceiling: number): number {
  let count = 0
  const stack: unknown[] = [root]
  while (stack.length > 0 && count <= ceiling) {
    const value = stack.pop()
    if (value === null || typeof value !== 'object') continue
    if (Array.isArray(value)) {
      for (const item of value) stack.push(item)
      continue
    }
    const node = value as Record<string, unknown>
    if (node.type === 'element') {
      count += 1
      for (const prop of Object.values((node.props ?? {}) as Record<string, unknown>)) {
        stack.push(prop)
      }
      continue
    }
    for (const prop of Object.values(node)) stack.push(prop)
  }
  return count
}

export type ViolationSeverity =
  /** Reactivity or a broken contract limit: the tree is not rendered. */
  | 'blocking'
  /**
   * Reported, not blocking. A dangling reference, a cycle the parser truncated,
   * or a statement nothing references. The old hand-written renderer degraded on
   * exactly these (drop the block, keep the siblings) and a lesson must not go
   * blank because the model wrote one paragraph nobody linked to — which the
   * backend validator does not reject either.
   */
  | 'structural'

export interface StaticViolation {
  severity: ViolationSeverity
  /** Stable machine code, for the telemetry counter of §14.2. */
  code: string
  /** Spanish, because it lands in a log a human reads. */
  message: string
}

export interface AssertOptions {
  /**
   * Relaxes the two structural checks only: mid-stream, `meta.unresolved`
   * legitimately holds forward references that have not arrived yet — measured, it
   * even holds *half-typed identifiers* (`unres: ["StepSequenc"]`) — and a
   * statement can be transiently orphaned. The reactivity checks never relax.
   */
  streaming?: boolean
  /**
   * Looks inside a statement that nothing references. `meta.orphaned` carries only
   * the *name*, so an orphan is the one place where reactivity is invisible to the
   * walk below: `z = Action([@OpenUrl("https://…")])` is not in the tree at all.
   * `gateProgram` supplies a probe that re-parses the program with the orphan
   * promoted to root; anything blocking it finds is attributed to the orphan.
   */
  probeOrphan?: (name: string) => StaticViolation[]
}

/**
 * Returns every reason the program is not a static tree. Empty array = clean.
 */
export function assertStaticOnly(
  result: ParseResult | null,
  { streaming = false, probeOrphan }: AssertOptions = {},
): StaticViolation[] {
  if (!result) return []

  const found: StaticViolation[] = []
  const block = (code: string, message: string) =>
    found.push({ severity: 'blocking', code, message })

  // ── Reactivity, declared at statement level ────────────────
  // Queries are the dangerous half: they self-fire in a `useEffect` as soon as
  // streaming ends, with no click, and take an unbounded `refreshInterval`.
  for (const query of result.queryStatements) {
    block('query', `Query prohibida (${query.statementId ?? '?'})`)
  }
  for (const mutation of result.mutationStatements) {
    block('mutation', `Mutation prohibida (${mutation.statementId ?? '?'})`)
  }
  for (const name of Object.keys(result.stateDeclarations ?? {})) {
    block('state', `estado $ prohibido (${name})`)
  }
  for (const error of result.meta.errors) {
    if (error.code === 'inline-reserved') {
      block('inline-reserved', `Query/Mutation inline (${error.statementId ?? '?'})`)
    }
  }

  // ── Contract rule 4 (§5.2), the only one visible from a ParseResult ──
  if (result.meta.statementCount > MAX_COMPONENTS) {
    block(
      'too-many-components',
      `${result.meta.statementCount} sentencias, el maximo del contrato es ${MAX_COMPONENTS}`,
    )
  }

  // ── Contract rule 4 (§5.2), painting half ─────────────────
  // `statementCount` is a count of components; this is a count of the elements they
  // expand to, which is a different number as soon as one id is referenced twice.
  const painted = countElements(result.root, MAX_RENDERED_ELEMENTS)
  if (painted > MAX_RENDERED_ELEMENTS) {
    block(
      'too-many-elements',
      `el arbol pinta mas de ${MAX_RENDERED_ELEMENTS} bloques ` +
        `(${result.meta.statementCount} sentencias reutilizadas por referencia)`,
    )
  }

  // ── Reactivity surviving inside props ─────────────────────
  // A resolved component is `type: "element"`, so a surviving `k: "Comp"` is a
  // builtin or an action — `@Count`, `@Each`, `Action`, `@OpenUrl`, `@ToAssistant`.
  const kinds = new Set<string>()
  const seen = new Set<unknown>()
  const walk = (value: unknown): void => {
    if (value === null || typeof value !== 'object') return
    if (seen.has(value)) return
    seen.add(value)
    if (Array.isArray(value)) {
      value.forEach(walk)
      return
    }
    const node = value as Record<string, unknown>
    if (node.__reactive) {
      kinds.add('binding reactivo')
      return
    }
    if (typeof node.k === 'string') {
      if (RUNTIME_KINDS.has(node.k)) kinds.add(`expresion ${node.k}`)
      if (node.k === 'Comp') kinds.add(`llamada no resuelta @${String(node.name ?? '?')}`)
      if (node.k === 'Ph') kinds.add(`placeholder ${String(node.n ?? '?')}`)
    }
    if (node.type === 'element') {
      Object.values((node.props ?? {}) as Record<string, unknown>).forEach(walk)
      return
    }
    Object.values(node).forEach(walk)
  }
  walk(result.root)
  for (const kind of kinds) block('runtime-expression', kind)

  // ── Statements nothing references ─────────────────────────
  if (!streaming && result.meta.orphaned.length > 0) {
    for (const name of result.meta.orphaned) {
      const inside = probeOrphan?.(name) ?? []
      for (const violation of inside) {
        block('orphaned-reactive', `${name}: ${violation.message}`)
      }
    }
    found.push({
      severity: 'structural',
      code: 'orphaned',
      message: `sentencias que nadie referencia: ${result.meta.orphaned.join(', ')}`,
    })
  }

  // ── Dangling references and truncated cycles ──────────────
  if (!streaming && result.meta.unresolved.length > 0) {
    found.push({
      severity: 'structural',
      code: 'unresolved',
      message: `referencias sin resolver o ciclo cortado: ${result.meta.unresolved.join(', ')}`,
    })
  }

  return found
}

/** True when at least one violation must stop the tree from being painted. */
export function isBlocked(violations: readonly StaticViolation[]): boolean {
  return violations.some((violation) => violation.severity === 'blocking')
}

/**
 * The gate's own parser.
 *
 * `<Renderer>` parses the program internally too, so the text is parsed twice per
 * change. That is deliberate: `onParseResult` fires in a `useEffect` *after* the
 * tree has mounted, which is too late to refuse to render it. Parsing ahead of the
 * runtime is what makes "a reactive program is never handed to the reactive
 * runtime" true rather than aspirational. `parse()` is pure, so one instance
 * serves every program (measured).
 */
const gateParser = createParser(skillnetLibrarySchema, 'Stack')

export interface GateResult {
  violations: StaticViolation[]
  /** True when the tree must not be rendered at all. */
  blocked: boolean
  /** True when the program yields no root yet — there is nothing to paint. */
  empty: boolean
}

const CLEAN: GateResult = { violations: [], blocked: false, empty: true }

/**
 * Parses the program the two ways the vendor can, because they disagree.
 *
 * MEASURED, and it was a real hole: on a duplicated statement id, `createParser`
 * resolves to the LAST declaration and the streaming parser `<Renderer>` uses
 * resolves to the FIRST. A program whose first `a = Action([@OpenUrl(…)])` is
 * followed by a benign `a = TextContent(…)` therefore looked clean to one parser
 * and rendered the action with the other. Gating on the union of both removes the
 * whole class, and does not depend on knowing which parser the runtime picks
 * internally — an implementation detail a patch release can change.
 *
 * The streaming parser is created fresh on every call: it is stateful by design.
 */
function parseBothWays(program: string): ParseResult[] {
  const results: ParseResult[] = [gateParser.parse(program)]
  results.push(createStreamingParser(skillnetLibrarySchema, 'Stack').set(program))
  return results
}

/**
 * Parses and gates a program in one step. This is what the renderer calls.
 */
export function gateProgram(
  program: string | null | undefined,
  { streaming = false }: { streaming?: boolean } = {},
): GateResult {
  if (!program || program.trim() === '') return CLEAN

  let parsed: ParseResult[]
  try {
    parsed = parseBothWays(program)
  } catch (error) {
    // The vendor wraps its own parse (it reports `parse-exception`), so reaching
    // here is unexpected. Fail closed: we cannot certify the program is static.
    return {
      blocked: true,
      empty: true,
      violations: [
        {
          severity: 'blocking',
          code: 'parse-exception',
          message: `el parser lanzo: ${error instanceof Error ? error.message : String(error)}`,
        },
      ],
    }
  }

  const seen = new Set<string>()
  const violations: StaticViolation[] = []
  for (const result of parsed) {
    for (const violation of assertStaticOnly(result, {
      streaming,
      probeOrphan: (name) => probeOrphan(program, name),
    })) {
      const key = `${violation.code}|${violation.message}`
      if (seen.has(key)) continue
      seen.add(key)
      violations.push(violation)
    }
  }

  return {
    violations,
    blocked: isBlocked(violations),
    empty: parsed.every((result) => result.root === null),
  }
}

/**
 * Re-parses the program with `name` promoted to the root so the prop walk can see
 * what the orphan actually holds.
 *
 * A duplicated `root` statement resolves to the LAST one (measured), so appending
 * a new root is enough — no text surgery, no regex over the source. The result is
 * used for analysis only, never rendered.
 */
function probeOrphan(program: string, name: string): StaticViolation[] {
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) return []
  try {
    const promoted = gateParser.parse(`${program}\nroot = Stack([${name}], "md")`)
    // No `probeOrphan` here: one level is enough and it cannot recurse.
    return assertStaticOnly(promoted, { streaming: true }).filter(
      (violation) => violation.severity === 'blocking',
    )
  } catch {
    return []
  }
}
