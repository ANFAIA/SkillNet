import { useId } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'
import { clickify, useClickableText } from '../ClickableText'
import { autolinkBareDomains } from './autolinkBareDomains'

// §5.2 rule 6: `props.text` is plain text or *inline* markdown (`**`, `*`,
// backticks, links). Never HTML. So we reuse react-markdown — already a
// dependency for `LessonContent` — but unwrap the block wrapper so the result
// can sit inside a <p>, a <td> or an <li> without nesting block elements.
const components: Components = {
  p: ({ children }) => <>{children}</>,
  strong: ({ children }) => <strong className="font-medium text-text">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  code: ({ children }) => (
    <code className="rounded bg-bg-muted px-1 py-0.5 text-[0.9em] font-mono text-text">
      {children}
    </code>
  ),
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-primary hover:underline">
      {children}
    </a>
  ),
  del: ({ children }) => <del>{children}</del>,
}

/**
 * The same map, with the paragraph splitting its finished subtree into word
 * spans (§8.5). Exactly one level does the splitting: `p` receives `strong`,
 * `em`, `code` and `a` already rendered and `clickify` walks *those*, so
 * clickifying inside them as well would nest a span inside a span. `code` and
 * `a` stay whole — they are in `OPAQUE_TAGS`.
 */
function clickableComponents(prefix: string): Components {
  return { ...components, p: ({ children }) => <>{clickify(children, prefix)}</> }
}

/**
 * Inline-only markdown. Headings, lists, tables and code fences are stripped to
 * their text content: the kit has dedicated components for all of them, so a
 * generated `text` prop that smuggles a `## heading` in should not create a
 * second visual hierarchy.
 *
 * Inside a `ClickableText` the words become clickable (§8.5). The wrapper cannot
 * do that from the outside: it would have to reach through this component
 * boundary, where `children` is still the raw string `ReactMarkdown` is about to
 * parse, so it would hand `ReactMarkdown` an array of spans. The opt-in travels
 * by context instead.
 */
export function InlineMarkdown({ children }: { children: string }) {
  const clickable = useClickableText()
  const prefix = useId().replace(/:/g, '')

  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={clickable ? clickableComponents(prefix) : components}
      allowedElements={['p', 'strong', 'em', 'code', 'a', 'del']}
      unwrapDisallowed
    >
      {autolinkBareDomains(children)}
    </ReactMarkdown>
  )
}
