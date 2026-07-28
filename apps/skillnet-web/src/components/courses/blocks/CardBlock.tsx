import type { ReactNode } from 'react'
import { Card, CardTitle } from '../../ui'
import { ClickableText } from '../ClickableText'

export interface CardBlockProps {
  title: string
  children?: ReactNode
}

/**
 * Grouping container. Reuses the v1 `Card` primitive rather than restyling a
 * div, so a spec block and a v1 panel are visually the same object.
 *
 * §8.5 says "titulos incluidos": the title is the one piece of text a Card owns,
 * and it is where the unfamiliar noun usually is. The children clickify
 * themselves — each is another block.
 *
 * The extra className adds a subtle shadow at rest that lifts on hover, giving
 * the card a sense of elevation without modifying the shared Card primitive.
 */
export function CardBlock({ title, children }: CardBlockProps) {
  return (
    <Card className="shadow-sm hover:shadow-md transition-shadow duration-200">
      {title ? (
        <CardTitle className="mb-3 pb-3 border-b border-border">
          <ClickableText>{title}</ClickableText>
        </CardTitle>
      ) : null}
      <div className="flex flex-col gap-3 min-w-0">{children}</div>
    </Card>
  )
}
