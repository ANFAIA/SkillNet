import { useState } from 'react'
import { useIntl } from 'react-intl'
import { Button } from '../../ui'
import { ClickableText } from '../ClickableText'

export interface HintRevealBlockProps {
  title: string
  hints: string[]
  solution: string
}

/** Didact progressive disclosure adapted to SkillNet's visual language. */
export function HintRevealBlock({ title, hints, solution }: HintRevealBlockProps) {
  const intl = useIntl()
  const [visibleHints, setVisibleHints] = useState(0)
  const [solutionVisible, setSolutionVisible] = useState(false)

  return (
    <section className="w-full rounded-lg border border-border bg-surface p-5">
      <h3 className="text-base font-semibold text-text"><ClickableText>{title}</ClickableText></h3>
      <div className="mt-4 space-y-3" aria-live="polite">
        {hints.slice(0, visibleHints).map((hint, index) => (
          <div key={index} className="rounded-lg bg-bg-muted px-4 py-3">
            <p className="text-xs font-medium text-text-muted">{intl.formatMessage({ id: 'didact.hint.label' }, { current: index + 1, total: hints.length })}</p>
            <ClickableText as="p" className="mt-1 text-sm text-text">{hint}</ClickableText>
          </div>
        ))}
        {solutionVisible && (
          <div className="rounded-lg border border-border px-4 py-3">
            <p className="text-xs font-medium text-text-muted">{intl.formatMessage({ id: 'didact.hint.solution' })}</p>
            <ClickableText as="p" className="mt-1 text-sm text-text">{solution}</ClickableText>
          </div>
        )}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {visibleHints < hints.length && (
          <Button type="button" variant="secondary" size="sm" onClick={() => setVisibleHints((value) => value + 1)}>
            {intl.formatMessage({ id: 'didact.hint.next' })}
          </Button>
        )}
        <Button type="button" variant="ghost" size="sm" aria-expanded={solutionVisible} onClick={() => setSolutionVisible((value) => !value)}>
          {intl.formatMessage({ id: solutionVisible ? 'didact.hint.hideSolution' : 'didact.hint.revealSolution' })}
        </Button>
      </div>
    </section>
  )
}
