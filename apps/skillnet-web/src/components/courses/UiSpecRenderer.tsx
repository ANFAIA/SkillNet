import { Fragment, useMemo, type ReactNode } from 'react'
import {
  CalloutBlock,
  CardBlock,
  ChartBlock,
  CodeBlockBlock,
  MarkdownBlock,
  QuizItemBlock,
  StackBlock,
  StepSequenceBlock,
  TableBlock,
  TextContentBlock,
} from './blocks'
import { UI_SPEC_VERSION, type RawUiComponent, type UiSpec } from '../../types/ui-spec'
import type { ExerciseType } from '../../types'
import type {
  BloomLevel,
  CalloutTone,
  ChartKind,
  StackGap,
  TextVariant,
} from '../../types/ui-spec'

const WARN = '[UiSpecRenderer]'

/**
 * Guards, not contract limits. The backend already enforces "max 12 components"
 * (§5.2 rule 4); these exist so a spec that reached the browser malformed — a
 * cycle, a self-reference, a diamond that fans out — cannot lock the tab.
 */
const MAX_DEPTH = 8
const MAX_RENDERED = 64

// ── Defensive prop readers ───────────────────────────────────
// Specs are validated server-side, but a browser holding an older bundle can
// receive a spec with a component or a prop shape it does not know. Every read
// below degrades to a safe default instead of throwing.

function readString(props: Record<string, unknown> | undefined, key: string, fallback = ''): string {
  const value = props?.[key]
  return typeof value === 'string' ? value : fallback
}

function readEnum<T extends string>(
  props: Record<string, unknown> | undefined,
  key: string,
  allowed: readonly T[],
  fallback: T,
): T {
  const value = props?.[key]
  return typeof value === 'string' && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : fallback
}

function readStringArray(props: Record<string, unknown> | undefined, key: string): string[] {
  const value = props?.[key]
  if (!Array.isArray(value)) return []
  return value.map((entry) => (typeof entry === 'string' ? entry : String(entry ?? '')))
}

function readStringMatrix(props: Record<string, unknown> | undefined, key: string): string[][] {
  const value = props?.[key]
  if (!Array.isArray(value)) return []
  return value.map((row) =>
    Array.isArray(row) ? row.map((cell) => (typeof cell === 'string' ? cell : String(cell ?? ''))) : [],
  )
}

function readNumberArray(props: Record<string, unknown> | undefined, key: string): number[] {
  const value = props?.[key]
  if (!Array.isArray(value)) return []
  return value.map((entry) => {
    const num = Number(entry)
    return Number.isFinite(num) ? num : 0
  })
}

const GAPS: readonly StackGap[] = ['sm', 'md', 'lg']
const TEXT_VARIANTS: readonly TextVariant[] = ['body', 'lead', 'caption']
const CALLOUT_TONES: readonly CalloutTone[] = ['info', 'warn', 'success']
const CHART_KINDS: readonly ChartKind[] = ['bar', 'line']
const EXERCISE_TYPES: readonly ExerciseType[] = [
  'test',
  'true_false',
  'fill_blank',
  'order_steps',
  'practical_case',
  'dialogue',
]
const BLOOM_LEVELS: readonly BloomLevel[] = [
  'remember',
  'understand',
  'apply',
  'analyze',
  'evaluate',
  'create',
]

interface RenderContext {
  byId: Map<string, RawUiComponent>
  nodeId: string
  renderId?: string
  /** Mutable render budget shared by the whole pass. */
  budget: { remaining: number }
}

/**
 * Resolves a list of child ids into nodes.
 *
 * `ancestors` is the current path, not a global visited set: a component may
 * legally appear twice in a spec (a diamond), but never inside itself.
 */
function renderChildren(
  ids: string[] | undefined,
  ctx: RenderContext,
  ancestors: readonly string[],
  depth: number,
): ReactNode {
  if (!Array.isArray(ids) || ids.length === 0) return null

  const nodes: ReactNode[] = []
  ids.forEach((childId, index) => {
    if (typeof childId !== 'string') {
      console.warn(`${WARN} child reference at index ${index} is not a string, skipped`)
      return
    }
    const node = renderById(childId, ctx, ancestors, depth)
    if (node !== null) {
      // Keyed by id AND index: the same id may legally appear twice in one list.
      nodes.push(<Fragment key={`${childId}:${index}`}>{node}</Fragment>)
    }
  })

  return nodes.length > 0 ? nodes : null
}

function renderById(
  id: string,
  ctx: RenderContext,
  ancestors: readonly string[],
  depth: number,
): ReactNode {
  if (ancestors.includes(id)) {
    console.warn(`${WARN} cycle detected at "${id}" (path: ${[...ancestors, id].join(' > ')})`)
    return null
  }
  if (depth > MAX_DEPTH) {
    console.warn(`${WARN} max depth ${MAX_DEPTH} exceeded at "${id}"`)
    return null
  }
  if (ctx.budget.remaining <= 0) {
    console.warn(`${WARN} render budget of ${MAX_RENDERED} components exhausted at "${id}"`)
    return null
  }

  const component = ctx.byId.get(id)
  if (!component) {
    // §5.2 rule 2 says every reference must resolve. A dangling one means the
    // spec is broken upstream; the learner still gets the rest of the screen.
    console.warn(`${WARN} unknown component id "${id}", skipped`)
    return null
  }

  ctx.budget.remaining -= 1
  const path = [...ancestors, id]
  const props = component.props
  const kids = () => renderChildren(component.children, ctx, path, depth + 1)

  switch (component.type) {
    case 'Stack':
      return <StackBlock gap={readEnum(props, 'gap', GAPS, 'md')}>{kids()}</StackBlock>

    case 'TextContent':
      return (
        <TextContentBlock
          text={readString(props, 'text')}
          variant={readEnum(props, 'variant', TEXT_VARIANTS, 'body')}
        />
      )

    case 'Card':
      return <CardBlock title={readString(props, 'title')}>{kids()}</CardBlock>

    case 'Callout':
      return (
        <CalloutBlock
          tone={readEnum(props, 'tone', CALLOUT_TONES, 'info')}
          text={readString(props, 'text')}
        />
      )

    case 'StepSequence':
      return (
        <StepSequenceBlock
          title={readString(props, 'title')}
          steps={readStringArray(props, 'steps')}
        />
      )

    case 'Table':
      return (
        <TableBlock
          headers={readStringArray(props, 'headers')}
          rows={readStringMatrix(props, 'rows')}
        />
      )

    case 'CodeBlock':
      return (
        <CodeBlockBlock
          language={readString(props, 'language')}
          code={readString(props, 'code')}
        />
      )

    case 'Chart':
      return (
        <ChartBlock
          kind={readEnum(props, 'kind', CHART_KINDS, 'bar')}
          title={readString(props, 'title')}
          labels={readStringArray(props, 'labels')}
          values={readNumberArray(props, 'values')}
        />
      )

    case 'QuizItem':
      return (
        <QuizItemBlock
          item_id={readString(props, 'item_id', component.id)}
          item_type={readEnum(props, 'item_type', EXERCISE_TYPES, 'test')}
          bloom_level={readEnum(props, 'bloom_level', BLOOM_LEVELS, 'apply')}
          question={readString(props, 'question')}
          options={readStringArray(props, 'options')}
          nodeId={ctx.nodeId}
          renderId={ctx.renderId}
        />
      )

    case 'Markdown':
      return <MarkdownBlock content={readString(props, 'content')} />

    default:
      // Frozen kit + newer server = unknown type. Log and drop the block; never
      // break the page (§5.5).
      console.warn(`${WARN} unsupported component type "${component.type}" (id "${component.id}")`)
      return null
  }
}

export interface UiSpecRendererProps {
  spec: UiSpec
  /** Node the spec belongs to — `QuizItemBlock` posts its answers there. */
  nodeId: string
  /**
   * `node_renders.id` of this spec. Required for a gradeable quiz item; when
   * omitted the quiz items render read-only (raw-spec preview, Storybook).
   */
  renderId?: string
}

/**
 * Renders a validated `UISpec` (§5.2) by walking `children` ids from `root`.
 *
 * Same dispatch shape as v1's `ExerciseRenderer`, with three hard guarantees the
 * v1 renderer never needed: a dangling id, a duplicate id and a cycle all
 * degrade to a warning plus a partial screen. Nothing here throws.
 */
export function UiSpecRenderer({ spec, nodeId, renderId }: UiSpecRendererProps) {
  const byId = useMemo(() => {
    const map = new Map<string, RawUiComponent>()
    const components: unknown = spec?.components
    if (!Array.isArray(components)) return map

    for (const entry of components as RawUiComponent[]) {
      if (!entry || typeof entry.id !== 'string' || typeof entry.type !== 'string') {
        console.warn(`${WARN} component without a string id/type, skipped`)
        continue
      }
      if (map.has(entry.id)) {
        // First declaration wins: it is the one `root` and any earlier
        // `children` array was written against.
        console.warn(`${WARN} duplicate component id "${entry.id}", keeping the first`)
        continue
      }
      map.set(entry.id, entry)
    }
    return map
  }, [spec])

  if (!spec || typeof spec.root !== 'string' || byId.size === 0) {
    console.warn(`${WARN} spec has no usable root or no components`)
    return null
  }
  if (spec.version && spec.version !== UI_SPEC_VERSION) {
    console.warn(`${WARN} spec version "${spec.version}" != "${UI_SPEC_VERSION}", rendering anyway`)
  }

  const tree = renderById(spec.root, { byId, nodeId, renderId, budget: { remaining: MAX_RENDERED } }, [], 0)
  if (tree === null) return null

  return (
    <div className="min-w-0" data-ui-format={spec.format}>
      {tree}
    </div>
  )
}
