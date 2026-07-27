/**
 * The click-to-explain surface (§8.3, §8.5).
 *
 * One listener over the whole subtree turns a click on a word, or a drag across a
 * phrase, into a selection the popover anchors to.
 *
 * **The hit-test is the first line of the handler, and it is not optional.** Curio's
 * original surface only ever wrapped chat prose, so it never had to tell "a click on
 * a word" from "a click on a control", and `justDragged` only separates a drag from a
 * click. Here the subtree contains buttons, radios and inputs: without the test,
 * answering a quiz option **also** fired an explanation of the option's own words —
 * which is a free, uncounted hint on the correct answer.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type { MouseEvent, ReactNode } from 'react'
import { centerContext } from '../../api/explain'
import { ExplainPopover } from './ExplainPopover'

/** The block a term's context is taken from (§8.3). */
export const BLOCK_SELECTOR = 'p,li,h1,h2,h3,h4,h5,h6,blockquote,td,th,dd,dt'

/**
 * Anything that is a control, a link, or explicitly opted out (§8.5). `QuizItemBlock`
 * carries `data-no-explain` on the whole item — statement *and* options — and
 * `CodeBlockBlock` does the same.
 */
export const NO_EXPLAIN_SELECTOR =
  'button, a, input, textarea, select, label, [role="radio"], [role="button"], [data-no-explain]'

/** Word characters, including the internal apostrophe/hyphen the tokenizer keeps. */
const WORD_CHAR = /[\p{L}\p{N}'’-]/u

/**
 * Snap both ends of a selection out to whole words, so half-selecting a word still
 * explains (and highlights) the complete word.
 */
export function expandRangeToWords(range: Range): void {
  const { startContainer, endContainer } = range
  if (startContainer.nodeType === Node.TEXT_NODE) {
    const text = startContainer.textContent ?? ''
    let start = range.startOffset
    while (start > 0 && WORD_CHAR.test(text[start - 1])) start--
    range.setStart(startContainer, start)
  }
  if (endContainer.nodeType === Node.TEXT_NODE) {
    const text = endContainer.textContent ?? ''
    let end = range.endOffset
    while (end < text.length && WORD_CHAR.test(text[end])) end++
    range.setEnd(endContainer, end)
  }
}

/**
 * The block's text **as a reader sees it**.
 *
 * A raw `textContent` also picks up decoration: `StepSequenceBlock` paints its
 * own list markers, so the context of step 2 came out as "2Escanear el ticket"
 * — a glued-on digit in the prompt, and a different `context_hash` than the same
 * sentence anywhere else, which silently halves the cache hit rate (§3.4).
 * Anything `aria-hidden` or opted out of explain is dropped first.
 */
function readableText(block: HTMLElement | null): string {
  if (!block) return ''
  const copy = block.cloneNode(true) as HTMLElement
  for (const noise of copy.querySelectorAll('[aria-hidden="true"], [data-no-explain]')) {
    noise.remove()
  }
  return copy.textContent ?? ''
}

export interface ExplainSelection {
  /** The clicked word or the selected phrase, verbatim. */
  term: string
  /** Normalized block text, 600 characters centered on the term. */
  context: string
  /** The word span, when a single word was clicked. */
  el: HTMLElement | null
  /** The snapped range, when a phrase was selected. */
  range: Range | null
  /** The block element the term sits in. */
  block: HTMLElement | null
  /**
   * True when the selection came from Enter/Space rather than the mouse. Only then
   * does the popover take focus: a keyboard user must be able to reach the "No lo
   * entiendo" button, a mouse user should keep the caret where they left it.
   */
  viaKeyboard: boolean
}

const PAD_X = 4
const PAD_Y = 2

interface LineRect {
  left: number
  top: number
  right: number
  bottom: number
}

/**
 * `range.getClientRects()` returns one rect per inline box — and every word is its
 * own span, so that is one rect per word and per space. Merge the ones that share a
 * line so the band paints as a continuous stripe instead of a row of pills.
 */
function mergeIntoLines(rects: DOMRect[]): LineRect[] {
  const lines: LineRect[] = []
  for (const rect of rects) {
    if (rect.width === 0 || rect.height === 0) continue
    const last = lines[lines.length - 1]
    if (last && rect.top < last.bottom - 2 && rect.bottom > last.top + 2) {
      last.left = Math.min(last.left, rect.left)
      last.top = Math.min(last.top, rect.top)
      last.right = Math.max(last.right, rect.right)
      last.bottom = Math.max(last.bottom, rect.bottom)
    } else {
      lines.push({ left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom })
    }
  }
  return lines
}

/**
 * Paints the selected phrase as a soft rounded band behind the text. The CSS Custom
 * Highlight API cannot do this: `::highlight()` supports neither padding nor
 * border-radius, so the band is measured and drawn as real elements.
 */
function PhraseBand({ range }: { range: Range | null }) {
  const [rects, setRects] = useState<LineRect[]>([])

  useEffect(() => {
    if (!range) {
      setRects([])
      return
    }
    let frame = 0
    const measure = () => {
      frame = 0
      setRects(mergeIntoLines(Array.from(range.getClientRects())))
    }
    measure()
    const onChange = () => {
      if (!frame) frame = requestAnimationFrame(measure)
    }
    // Capture phase, so scrolling inside an inner pane is caught too.
    window.addEventListener('scroll', onChange, true)
    window.addEventListener('resize', onChange)
    return () => {
      window.removeEventListener('scroll', onChange, true)
      window.removeEventListener('resize', onChange)
      if (frame) cancelAnimationFrame(frame)
    }
  }, [range])

  if (!range || rects.length === 0) return null

  return createPortal(
    <div className="phrase-layer" aria-hidden="true">
      {rects.map((rect, index) => (
        <span
          key={index}
          className="phrase-rect"
          style={{
            left: `${rect.left - PAD_X}px`,
            top: `${rect.top - PAD_Y}px`,
            width: `${rect.right - rect.left + PAD_X * 2}px`,
            height: `${rect.bottom - rect.top + PAD_Y * 2}px`,
          }}
        />
      ))}
    </div>,
    document.body,
  )
}

export interface ClickableSurfaceProps {
  children: ReactNode
  /** Sent as `node_id`; the server adds the node's title and summary to the prompt. */
  nodeId?: string | null
  language?: string
  className?: string
}

export function ClickableSurface({
  children,
  nodeId = null,
  language,
  className,
}: ClickableSurfaceProps) {
  const ref = useRef<HTMLDivElement>(null)
  // Set when a drag just produced a selection, so the trailing click a short drag
  // also fires does not overwrite the phrase with a single word. Cleared next tick.
  const justDragged = useRef(false)
  const [selection, setSelection] = useState<ExplainSelection | null>(null)

  const blockContext = useCallback((node: Node | null, term: string): string => {
    const element = node instanceof Element ? node : node?.parentElement
    const block = (element?.closest(BLOCK_SELECTOR) as HTMLElement | null) ?? ref.current
    return centerContext(readableText(block), term)
  }, [])

  const close = useCallback(() => setSelection(null), [])

  // Escape closes from anywhere, including while the popover has focus.
  useEffect(() => {
    if (!selection) return
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') setSelection(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [selection])

  // Keep the open word visibly and semantically marked, then clean up after itself.
  useEffect(() => {
    const el = selection?.el
    if (!el) return
    el.classList.add('entity-open')
    el.setAttribute('aria-expanded', 'true')
    return () => {
      el.classList.remove('entity-open')
      el.removeAttribute('aria-expanded')
    }
  }, [selection])

  const onClick = useCallback(
    (event: MouseEvent<HTMLDivElement>) => {
      // §8.5, first line: a control is never a term.
      if ((event.target as HTMLElement).closest(NO_EXPLAIN_SELECTOR)) return

      if (justDragged.current) {
        justDragged.current = false
        return // the tail of a drag we already handled
      }
      const native = window.getSelection()
      if (native && !native.isCollapsed && native.toString().trim()) return

      const entity = (event.target as HTMLElement).closest('.entity')
      if (!(entity instanceof HTMLElement) || !ref.current?.contains(entity)) return
      const term = entity.textContent?.trim() ?? ''
      if (!term) return

      setSelection({
        term,
        context: blockContext(entity, term),
        el: entity,
        range: null,
        block: (entity.closest(BLOCK_SELECTOR) as HTMLElement | null) ?? ref.current,
        // A programmatic click (`ClickableText`'s Enter/Space path) has detail 0;
        // a real mouse click never does.
        viaKeyboard: event.detail === 0,
      })
    },
    [blockContext],
  )

  const onMouseUp = useCallback(
    (event: MouseEvent<HTMLDivElement>) => {
      // A drag that ends on a control is not a term either.
      if ((event.target as HTMLElement).closest(NO_EXPLAIN_SELECTOR)) return

      const native = window.getSelection()
      if (!native || native.isCollapsed || native.rangeCount === 0) return
      const liveRange = native.getRangeAt(0)
      if (!ref.current?.contains(liveRange.commonAncestorContainer)) return

      const range = liveRange.cloneRange()
      expandRangeToWords(range) // a 2+ word selection is explained as one unit
      const term = range.toString().trim()
      if (!term) return

      const node = range.commonAncestorContainer
      const block =
        ((node instanceof Element ? node : node.parentElement)?.closest(
          BLOCK_SELECTOR,
        ) as HTMLElement | null) ?? ref.current

      setSelection({
        term,
        context: blockContext(node, term),
        el: null,
        range,
        block,
        viaKeyboard: false,
      })

      // Drop the native selection so only our own band shows (no double band).
      native.removeAllRanges()
      justDragged.current = true
      setTimeout(() => {
        justDragged.current = false
      }, 0)
    },
    [blockContext],
  )

  return (
    <div ref={ref} onClick={onClick} onMouseUp={onMouseUp} className={className}>
      {children}
      <PhraseBand range={selection?.range ?? null} />
      {selection && (
        <ExplainPopover
          selection={selection}
          nodeId={nodeId}
          language={language}
          onClose={close}
        />
      )}
    </div>
  )
}
