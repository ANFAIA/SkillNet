import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'

/**
 * The caret, as a character rather than an element.
 *
 * A `<span>` cannot be appended *inside* the last paragraph of a markdown tree
 * without knowing which node is last, and "last" changes on every token — it is a
 * `<p>` one moment and an `<li>` inside a `<ul>` the next. Appending the glyph to
 * the markdown **source** puts it exactly where the text ends, in whatever element
 * the parser happens to be building, including a table cell.
 *
 * It is also why the old `animate-pulse` caret is gone, which is a small win: it
 * animated unconditionally, ignoring `useReducedMotion` (OS *or* declared), and a
 * blinking bar is precisely the kind of motion a learner switches off.
 */
const CARET = '▍'

/**
 * Chat-bubble markdown.
 *
 * ## Why this is not `LessonContent`
 *
 * `LessonContent` is the *lesson* map: `text-secondary` body, 24 px heading rhythm,
 * `mb-3` under every block. Dropped into a bubble it reads as a document someone
 * pasted into a chat — washed out against `bg-bg-muted`, and with a trailing margin
 * the bubble's own padding then doubles. This map is the same idea at bubble scale:
 * colour inherited from the bubble, tighter rhythm, and **no margin under the last
 * child**, so the overwhelmingly common one-paragraph answer is pixel-identical to
 * the plain `<p>` it replaces. Only the answers that actually use markdown change.
 *
 * ## Why markdown is rendered while the answer is still streaming
 *
 * Because the half-written state is the state the learner spends the most time
 * looking at. Deferring the parse to `done` would show `1. **Escucha la pregunta**`
 * as literal asterisks for the whole stream and then snap — which is the reported
 * bug, just shorter. remark re-parses a ~1 KB document per token; measured on the
 * real 278-token answer that is not visible next to React's own re-render.
 *
 * ## What is deliberately not rendered
 *
 * No `rehype-raw`, so HTML in the model's output stays inert text — the default, and
 * it stays the default. `img` is disallowed on top of that: an image is the one
 * markdown construct that makes an unattended request to an arbitrary host the
 * moment it paints, and this text is downstream of a document anybody can upload.
 * `href` is left to react-markdown's own URL transform, which already drops
 * `javascript:`.
 */
const components: Components = {
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,

  // Chat answers are not documents: every heading level collapses onto one step of
  // emphasis rather than opening a hierarchy inside a 70%-wide bubble.
  h1: ({ children }) => <p className="font-semibold mt-3 mb-1.5 first:mt-0">{children}</p>,
  h2: ({ children }) => <p className="font-semibold mt-3 mb-1.5 first:mt-0">{children}</p>,
  h3: ({ children }) => <p className="font-semibold mt-3 mb-1.5 first:mt-0">{children}</p>,
  h4: ({ children }) => <p className="font-semibold mt-3 mb-1.5 first:mt-0">{children}</p>,
  h5: ({ children }) => <p className="font-semibold mt-3 mb-1.5 first:mt-0">{children}</p>,
  h6: ({ children }) => <p className="font-semibold mt-3 mb-1.5 first:mt-0">{children}</p>,

  ul: ({ children }) => (
    <ul className="list-disc pl-5 space-y-1 mb-2 last:mb-0 marker:text-text-muted">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal pl-5 space-y-1 mb-2 last:mb-0 marker:text-text-muted">
      {children}
    </ol>
  ),
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,

  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  del: ({ children }) => <del className="opacity-70">{children}</del>,

  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="underline underline-offset-2 hover:opacity-80"
    >
      {children}
    </a>
  ),

  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-border-strong pl-3 italic mb-2 last:mb-0">
      {children}
    </blockquote>
  ),

  code: ({ children }) => (
    <code className="rounded bg-bg px-1 py-0.5 text-[0.9em] font-mono">{children}</code>
  ),
  // The inline pill above is neutralised inside a fence rather than branched on:
  // react-markdown ≥ 9 no longer tells the `code` renderer whether it is inline, and
  // a fence with no language has no `className` to sniff either.
  pre: ({ children }) => (
    <pre className="rounded-lg bg-bg p-2.5 mb-2 last:mb-0 overflow-x-auto text-xs font-mono [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-[1em]">
      {children}
    </pre>
  ),

  // A bubble is 70% of a column: a table has to be allowed to scroll on its own
  // rather than widen its parent, which is the one thing a chat log must never do.
  table: ({ children }) => (
    <div className="overflow-x-auto mb-2 last:mb-0">
      <table className="w-full text-xs border-collapse">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="text-left py-1.5 px-2 border-b border-border-strong font-medium whitespace-nowrap">
      {children}
    </th>
  ),
  td: ({ children }) => <td className="py-1.5 px-2 border-b border-border align-top">{children}</td>,

  hr: () => <hr className="border-border my-3" />,
}

export interface ChatMarkdownProps {
  /** The assistant's prose, as the model wrote it. */
  content: string
  /** Appends the caret while tokens are still arriving. */
  isStreaming?: boolean
}

/**
 * `memo` because the bubble re-renders on every token of *any* message in the log,
 * and only the one whose `content` grew needs to re-parse.
 */
export const ChatMarkdown = memo(function ChatMarkdown({
  content,
  isStreaming = false,
}: ChatMarkdownProps) {
  return (
    <div className="min-w-0 break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={components}
        disallowedElements={['img']}
        unwrapDisallowed
      >
        {isStreaming && content ? `${content}${CARET}` : content}
      </ReactMarkdown>
    </div>
  )
})
