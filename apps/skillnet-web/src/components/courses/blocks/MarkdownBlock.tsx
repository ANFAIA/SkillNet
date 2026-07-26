import { LessonContent } from '../LessonContent'

export interface MarkdownBlockProps {
  content: string
}

/**
 * `fallback_seed` only — the LLM cannot emit `Markdown` (§5.3). It exists so the
 * "never a red screen" path can serve `lessons.content` verbatim through the
 * same renderer, which is why it reuses v1's `LessonContent` untouched.
 */
export function MarkdownBlock({ content }: MarkdownBlockProps) {
  return <LessonContent markdown={content} />
}
