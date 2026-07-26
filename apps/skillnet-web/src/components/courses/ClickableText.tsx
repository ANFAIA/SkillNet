/**
 * Turns already-rendered prose into clickable words (§8.1, §8.2).
 *
 * **The key to the port.** The markdown is never tokenized: `react-markdown` parses
 * and builds the tree as usual, and only the `typeof child === 'string'` leaves of
 * that finished tree are split into word spans. Emphasis, links, lists and tables
 * therefore survive untouched, and no `rehype-raw` is involved — the raw-HTML plugin
 * is the XSS vector this feature must not open.
 *
 * `ClickableText` also carries the third mandatory correction of §8.2, keyboard
 * access. Individual words deliberately get **no** `tabindex` (a long node would
 * flood the tab order with 300 stops). Instead each block is one tab stop with
 * `role="group"`, and inside it the arrow keys move a logical cursor between
 * clickable words while Enter/Space opens the explanation. That is the standard
 * roving-tabindex + `aria-activedescendant` pattern, not a `div` with an `onClick`.
 *
 * Activation is a synthetic `click()` on the active span, so the keyboard path goes
 * through exactly the same handler (and the same §8.5 hit-test) as the mouse path.
 * There is only ever one code path that can open an explanation.
 */

import {
  cloneElement,
  createContext,
  isValidElement,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
} from 'react'
import type { ElementType, KeyboardEvent, ReactElement, ReactNode } from 'react'
import { tokenize } from '../../lib/tokenize'

/** Class the surface's hit-test looks for. */
export const ENTITY_CLASS = 'entity'

/**
 * Inline tags whose text must never become clickable: code and links have their own
 * meaning, and the interactive ones are already excluded by the surface's hit-test —
 * decorating them would only promise something that does not happen.
 */
const OPAQUE_TAGS = new Set([
  'code',
  'pre',
  'kbd',
  'samp',
  'a',
  'button',
  'input',
  'textarea',
  'select',
  'label',
  'svg',
])

/** Guard against a pathologically deep tree; markdown never nests this far. */
const MAX_DEPTH = 12

/**
 * Split one string into inline spans: content words get `.entity`, everything else
 * (spaces, punctuation, emoji, stopwords) stays a plain span so text selection reads
 * as one continuous run.
 *
 * Defensive on input: a generated spec can leave a text prop `null` or hand us a
 * number, and a bad prop must never crash the lesson.
 */
export function toClickable(text: unknown, keyPrefix = 't'): ReactNode[] {
  const str = typeof text === 'string' ? text : text == null ? '' : String(text)
  return tokenize(str).map((token, index) =>
    token.clickable ? (
      <span key={`${keyPrefix}-${index}`} className={ENTITY_CLASS}>
        {token.text}
      </span>
    ) : (
      <span key={`${keyPrefix}-${index}`}>{token.text}</span>
    ),
  )
}

type ElementWithChildren = ReactElement<{
  children?: ReactNode
  'data-no-explain'?: unknown
}>

function isOpaque(node: ElementWithChildren): boolean {
  // A composite component is a boundary the walk cannot see past: its `children`
  // prop is its *input*, not its rendered output, so cloning it with word spans
  // would hand `<InlineMarkdown>` an array where it declared a string. Components
  // opt in for themselves instead, by reading `useClickableText()` — which is why
  // wrapping a block in `<ClickableText>` still makes its markdown clickable.
  if (typeof node.type !== 'string') return true
  if (OPAQUE_TAGS.has(node.type)) return true
  return node.props['data-no-explain'] !== undefined
}

/**
 * Walk a rendered subtree and replace only its string leaves. Elements are cloned
 * rather than re-created, so their type, props and keys are preserved exactly.
 */
export function clickify(node: ReactNode, path: string, depth = MAX_DEPTH): ReactNode {
  if (typeof node === 'string') return toClickable(node, path)
  if (Array.isArray(node)) {
    return node.map((child, index) => clickify(child, `${path}-${index}`, depth))
  }
  if (depth <= 0 || !isValidElement(node)) return node

  const element = node as ElementWithChildren
  if (isOpaque(element)) return node
  const children = element.props.children
  if (children === undefined || children === null) return node

  return cloneElement(element, undefined, clickify(children, path, depth - 1))
}

const ARROW_FORWARD = new Set(['ArrowRight', 'ArrowDown'])
const ARROW_BACK = new Set(['ArrowLeft', 'ArrowUp'])

/**
 * True inside a `ClickableText`. Components that render their own text — today
 * `InlineMarkdown` — read it and split their own string leaves, because the walk
 * above stops at every composite boundary.
 */
const ClickableTextContext = createContext(false)

export function useClickableText(): boolean {
  return useContext(ClickableTextContext)
}

export interface ClickableTextProps {
  children: ReactNode
  /** Extra classes for the group wrapper. */
  className?: string
  /** Accessible name of the group; defaults to the keyboard instructions. */
  label?: string
  /**
   * Tag the group renders as. `span` by default, which is what inline prose
   * wants; a block whose content is flow content (a `<table>`, an `<ol>`, or the
   * paragraph itself) must say so, because a `<span>` around them is invalid
   * HTML. The group **is** the block element in that case, so `BLOCK_SELECTOR`
   * still finds exactly one context per clicked word.
   */
  as?: 'span' | 'div' | 'p'
}

const DEFAULT_LABEL =
  'Texto explorable. Usa las flechas para elegir una palabra y Enter para ver su explicacion.'

/**
 * Wrap rendered prose so its words are clickable and reachable from the keyboard.
 * One tab stop per block; `aria-activedescendant` tells assistive tech which word
 * the logical cursor is on.
 */
export function ClickableText({
  children,
  className,
  label,
  as = 'span',
}: ClickableTextProps) {
  const ref = useRef<HTMLElement>(null)
  const groupId = useId().replace(/:/g, '')
  const [cursor, setCursor] = useState(-1)
  const [activeId, setActiveId] = useState<string | undefined>(undefined)

  const words = useCallback((): HTMLElement[] => {
    const root = ref.current
    if (!root) return []
    return Array.from(root.querySelectorAll<HTMLElement>(`.${ENTITY_CLASS}`))
  }, [])

  // Ids are assigned after render rather than threaded through `clickify`, because
  // the walk does not know how many spans came before it in sibling subtrees.
  useEffect(() => {
    const list = words()
    list.forEach((span, index) => {
      span.id = `${groupId}-w${index}`
    })
    list.forEach((span, index) => {
      if (index === cursor) span.setAttribute('data-cursor', 'true')
      else span.removeAttribute('data-cursor')
    })
    setActiveId(cursor >= 0 && list[cursor] ? list[cursor].id : undefined)
  }, [children, cursor, groupId, words])

  const move = useCallback(
    (delta: number) => {
      const list = words()
      if (list.length === 0) return
      setCursor((current) => {
        const next = current < 0 ? (delta > 0 ? 0 : list.length - 1) : current + delta
        return Math.min(list.length - 1, Math.max(0, next))
      })
    },
    [words],
  )

  const onKeyDown = useCallback(
    (event: KeyboardEvent<HTMLElement>) => {
      if (ARROW_FORWARD.has(event.key)) {
        event.preventDefault()
        move(1)
        return
      }
      if (ARROW_BACK.has(event.key)) {
        event.preventDefault()
        move(-1)
        return
      }
      if (event.key === 'Home' || event.key === 'End') {
        const list = words()
        if (list.length === 0) return
        event.preventDefault()
        setCursor(event.key === 'Home' ? 0 : list.length - 1)
        return
      }
      if (event.key === 'Enter' || event.key === ' ') {
        const target = words()[cursor]
        if (!target) return
        event.preventDefault()
        // Same handler, same hit-test, same result as a mouse click.
        target.click()
      }
    },
    [cursor, move, words],
  )

  const Tag = as as ElementType

  return (
    <ClickableTextContext.Provider value={true}>
      <Tag
        ref={ref}
        role="group"
        tabIndex={0}
        aria-label={label ?? DEFAULT_LABEL}
        aria-activedescendant={activeId}
        onKeyDown={onKeyDown}
        onBlur={() => setCursor(-1)}
        className={className ? `clickable-text ${className}` : 'clickable-text'}
      >
        {clickify(children, groupId, MAX_DEPTH)}
      </Tag>
    </ClickableTextContext.Provider>
  )
}
