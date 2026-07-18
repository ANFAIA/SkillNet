import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Components } from 'react-markdown'

// Markdown renderer mapped to design tokens (no typography plugin needed).
const components: Components = {
  h1: ({ children }) => <h1 className="text-lg font-semibold text-text mt-6 mb-3 first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="text-base font-semibold text-text mt-6 mb-2 first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="text-sm font-semibold text-text mt-4 mb-2">{children}</h3>,
  p: ({ children }) => <p className="text-sm text-text-secondary leading-relaxed mb-3">{children}</p>,
  ul: ({ children }) => <ul className="list-disc pl-5 space-y-1 mb-3 text-sm text-text-secondary">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 space-y-1 mb-3 text-sm text-text-secondary">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-text">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-primary hover:underline">
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-border pl-4 italic text-text-secondary mb-3">{children}</blockquote>
  ),
  code: ({ children }) => (
    <code className="rounded bg-bg-muted px-1.5 py-0.5 text-xs font-mono text-text">{children}</code>
  ),
  pre: ({ children }) => (
    <pre className="rounded-lg bg-bg-muted p-3 overflow-x-auto text-xs font-mono text-text mb-3">{children}</pre>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto mb-3">
      <table className="w-full text-sm border-collapse">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="text-left py-2 px-3 border-b border-border font-medium text-text-secondary">{children}</th>
  ),
  td: ({ children }) => <td className="py-2 px-3 border-b border-border text-text">{children}</td>,
  hr: () => <hr className="border-border my-4" />,
}

export function LessonContent({ markdown }: { markdown: string }) {
  return (
    <div className="min-w-0">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {markdown}
      </ReactMarkdown>
    </div>
  )
}
