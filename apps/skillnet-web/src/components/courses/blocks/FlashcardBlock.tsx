import { useState } from 'react'
import { useIntl } from 'react-intl'
import { Button } from '../../ui'
import { ClickableText } from '../ClickableText'

export interface FlashcardBlockProps {
  front: string
  back: string
}

/**
 * Didact Flashcard adapted to SkillNet's existing primitives and tokens.
 * The answer is revealed before recall can be rated; reduced-motion users get
 * an immediate state change. Rating remains local until SkillNet adopts the
 * neutral Didact event envelope.
 */
export function FlashcardBlock({ front, back }: FlashcardBlockProps) {
  const intl = useIntl()
  const [revealed, setRevealed] = useState(false)
  const [rating, setRating] = useState<'known' | 'review' | null>(null)

  return (
    <section className="w-full rounded-lg border border-border bg-surface p-5" data-revealed={revealed}>
      <div className="grid [perspective:1000px]">
        <div className={`col-start-1 row-start-1 grid [transform-style:preserve-3d] transition-transform duration-200 motion-reduce:transition-none ${revealed ? '[transform:rotateY(180deg)]' : ''}`}>
          <div className="col-start-1 row-start-1 flex min-h-32 flex-col items-center justify-center gap-4 text-center [backface-visibility:hidden]" aria-hidden={revealed} inert={revealed || undefined}>
            <ClickableText as="p" className="text-base font-medium text-text">{front}</ClickableText>
            <Button type="button" onClick={() => setRevealed(true)} aria-expanded={revealed}>
              {intl.formatMessage({ id: 'didact.flashcard.reveal' })}
            </Button>
          </div>
          <div className="col-start-1 row-start-1 flex min-h-32 items-center justify-center text-center [backface-visibility:hidden] [transform:rotateY(180deg)]" aria-hidden={!revealed} inert={!revealed || undefined}>
            <ClickableText as="p" className="text-base text-text">{back}</ClickableText>
          </div>
        </div>
      </div>
      {revealed && (
        <div className="mt-5 flex justify-center gap-2 border-t border-border pt-4" role="group" aria-label={intl.formatMessage({ id: 'didact.flashcard.rate' })}>
          <Button type="button" variant={rating === 'known' ? 'primary' : 'secondary'} size="sm" aria-pressed={rating === 'known'} onClick={() => setRating('known')}>
            {intl.formatMessage({ id: 'didact.flashcard.known' })}
          </Button>
          <Button type="button" variant={rating === 'review' ? 'primary' : 'secondary'} size="sm" aria-pressed={rating === 'review'} onClick={() => setRating('review')}>
            {intl.formatMessage({ id: 'didact.flashcard.review' })}
          </Button>
        </div>
      )}
    </section>
  )
}
