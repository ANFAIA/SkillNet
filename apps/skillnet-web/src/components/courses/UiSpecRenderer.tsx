import { useEffect, useMemo, useRef } from 'react'
import { Renderer } from '@openuidev/react-lang'
import type { OpenUIError } from '@openuidev/react-lang'

import { ErrorBoundary } from '../ErrorBoundary'
import { gateProgram, type StaticViolation } from './kit/assertStaticOnly'
import { nodeRenderContext } from './kit/NodeRenderContext'
import { skillnetLibrary } from './kit/library'
import type { UiFormat } from '../../types/node-render'

const WARN = '[UiSpecRenderer]'

export interface UiSpecRendererProps {
  /**
   * The lesson as OpenUI Lang **text**.
   *
   * ARCHITECTURAL RULE, and the one that matters most in this file: this must be
   * the program **re-serialized from the already-validated `UISpec`**, never the
   * model's `raw_dsl`. `<Renderer response>` only accepts text, and the tempting
   * shortcut is to forward whatever the model wrote. That would put
   * attacker-directed text — a poisoned PDF is the attack path — straight into a
   * reactive runtime, jumping every barrier at once. A `UISpec` cannot represent
   * an AST, so round-tripping through it is a structural guarantee rather than a
   * check that can be forgotten. `raw_dsl` stays in the model
   * (`src/models/node_render.py`) and in no response schema.
   *
   * `null` while the render is still loading.
   */
  program: string | null
  /** Node the program belongs to — `QuizItemBlock` posts its answers there. */
  nodeId: string
  /**
   * `node_renders.id` of this program. Required for a gradeable quiz item; when
   * omitted the quiz items render read-only (preview, Storybook).
   */
  renderId?: string
  /**
   * True while the program is still arriving over SSE. Passed straight through:
   * the runtime disables form interaction and keeps the last good subtree while
   * it re-parses each chunk.
   */
  isStreaming?: boolean
  /** `node_renders.ui_format`, surfaced as `data-ui-format` for §9.2 and tests. */
  format?: UiFormat
  /**
   * Structural-gate telemetry (§14.2). Called with every violation, blocking or
   * not; a non-empty `blocking` list means somebody handed the browser a program
   * with reactivity in it, which the trusted pipeline cannot produce.
   */
  onViolations?: (violations: StaticViolation[]) => void
  /**
   * Parser and runtime errors in the vendor's LLM-friendly shape — the input to
   * the repair loop of §5.4. Fired with `[]` once everything resolves.
   */
  onError?: (errors: OpenUIError[]) => void
}

/**
 * Renders a lesson with OpenUI's own runtime (`@openuidev/react-lang`).
 *
 * ## Reactivity: off, by omission of props
 *
 * The mandatory security profile is "sin reactividad", and it is enforced here by
 * what is NOT passed to `<Renderer>`:
 *
 * - no `toolProvider` → `createQueryManager(null)` and the two guards inside
 *   lang-core cut every `Query` and `Mutation` to zero. There is no other network
 *   egress in the package: the audit found no `fetch`, `XMLHttpRequest`,
 *   `WebSocket`, `sendBeacon`, `window.open`, `location`, `localStorage`,
 *   `document.cookie`, `eval` or `new Function` in either bundle.
 * - no `onAction` → `@OpenUrl` and `@ToAssistant` are no-ops. The runtime never
 *   navigates itself; it forwards the intent to that prop and nothing else.
 * - no `onStateUpdate` → `@Set` is persisted nowhere.
 * - and no component in the library calls `useTriggerAction()`, which is what
 *   makes an `ActionPlan` physically unfirable.
 *
 * On top of that, `gateProgram` parses the text *before* the runtime does and
 * refuses to hand it over at all if any of the above is in it.
 *
 * ## Robustness, kept from the hand-written renderer
 *
 * A dangling reference, a duplicate id and a cycle all degrade to a partial
 * screen: the vendor's parser drops the unresolvable child and reports it in
 * `meta.unresolved`, and truncates a cycle instead of recursing. A component that
 * is not in the library is not painted. A throw inside a single component is
 * caught by the runtime's per-element boundary, and anything it misses is caught
 * by ours — this component never throws at its caller.
 *
 * The hand-written renderer's `MAX_RENDERED` budget is back too, as
 * `MAX_RENDERED_ELEMENTS` in the gate: twelve components are a DAG, not a tree, so
 * counting components bounds nothing (measured: 370 bytes of legal program expand to
 * 29 526 elements). The cap that actually protects the tab is the server's
 * `MAX_RENDERED_NODES`, because at higher fan-out the *parse* dies of a V8 heap OOM,
 * which no `try/catch` can intercept; the gate's copy is the fail-closed half.
 *
 * `ClickableSurface` (§8.5) still wraps this component from the outside, in
 * `NodeView`; the hit-test is unchanged and the `data-no-explain` markers live
 * where they always did, inside the blocks.
 */
export function UiSpecRenderer({
  program,
  nodeId,
  renderId,
  isStreaming = false,
  format,
  onViolations,
  onError,
}: UiSpecRendererProps) {
  const gate = useMemo(() => gateProgram(program, { streaming: isStreaming }), [program, isStreaming])
  const target = useMemo(() => ({ nodeId, renderId }), [nodeId, renderId])

  const onViolationsRef = useRef(onViolations)
  onViolationsRef.current = onViolations

  useEffect(() => {
    if (gate.violations.length === 0) return
    for (const violation of gate.violations) {
      console.warn(`${WARN} ${violation.severity} ${violation.code}: ${violation.message}`)
    }
    onViolationsRef.current?.(gate.violations)
  }, [gate])

  // `empty` is the "no usable root" case: nothing to paint, so not even the
  // wrapper is emitted.
  if (!program || gate.blocked || gate.empty) return null

  return (
    <nodeRenderContext.Provider value={target}>
      <div className="min-w-0" data-ui-format={format}>
        <ErrorBoundary fallback={() => null}>
          <Renderer
            response={program}
            library={skillnetLibrary}
            isStreaming={isStreaming}
            onError={onError}
            // toolProvider, onAction and onStateUpdate are ABSENT on purpose.
            // See the "Reactivity" section above before adding any of them.
          />
        </ErrorBoundary>
      </div>
    </nodeRenderContext.Provider>
  )
}
