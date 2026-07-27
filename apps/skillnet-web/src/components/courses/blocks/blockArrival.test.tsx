import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import type { ReactNode } from 'react'

/**
 * How a generated lesson enters, tested where it is decided rather than where it moves.
 *
 * The animation itself is CSS (`.block-arrival` in `index.css`) and there is nothing
 * useful to assert about a tween. What matters, and what silently breaks, is *when the
 * class is applied*:
 *
 * 1. **Only on the root Stack.** Every program is a tree of Stacks (§5.2 rule 1). If a
 *    nested one staggered too, its children would be delayed by their own cadence *and*
 *    their parent's, so the last block of a two-level lesson would land half a second
 *    after the first — which reads as the page still loading.
 * 2. **Never in a preview.** Storybook and the admin preview render a static program
 *    that nobody waited for; the default is off, and it has to stay off by default
 *    rather than by every caller remembering to say so.
 * 3. **Never under reduced motion.** The stylesheet drops the animation for
 *    `prefers-reduced-motion`, but the learner who ticked "Menos animaciones" in the
 *    wizard has no media query — only this branch protects them.
 */

let reduceMotion = false

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual<typeof import('framer-motion')>('framer-motion')
  return { ...actual, useReducedMotion: () => reduceMotion }
})

const { StackBlock } = await import('./StackBlock')
const { blockArrivalContext } = await import('./blockArrival')
const { TextContentBlock } = await import('./TextContentBlock')

function arriving(children: ReactNode) {
  return (
    <blockArrivalContext.Provider value={true}>{children}</blockArrivalContext.Provider>
  )
}

function stacks(container: HTMLElement) {
  return Array.from(container.querySelectorAll('div.flex.flex-col'))
}

beforeEach(() => {
  reduceMotion = false
})

describe('block arrival', () => {
  it('staggers the root Stack of a lesson that just landed', () => {
    const { container } = render(
      arriving(
        <StackBlock gap="md">
          <TextContentBlock text="Primero." />
          <TextContentBlock text="Segundo." />
        </StackBlock>,
      ),
    )

    expect(stacks(container)[0].className).toContain('block-arrival')
  })

  it('staggers it once, not once per level of nesting', () => {
    const { container } = render(
      arriving(
        <StackBlock gap="md">
          <StackBlock gap="sm">
            <TextContentBlock text="Anidado." />
          </StackBlock>
        </StackBlock>,
      ),
    )

    const [root, nested] = stacks(container)
    expect(root.className).toContain('block-arrival')
    expect(nested.className).not.toContain('block-arrival')
  })

  it('does not animate a program nobody waited for', () => {
    const { container } = render(
      <StackBlock gap="md">
        <TextContentBlock text="Contenido estatico." />
      </StackBlock>,
    )

    expect(stacks(container)[0].className).not.toContain('block-arrival')
  })

  it('does not animate under reduced motion, even on arrival', () => {
    reduceMotion = true
    const { container } = render(
      arriving(
        <StackBlock gap="md">
          <TextContentBlock text="Primero." />
        </StackBlock>,
      ),
    )

    const root = stacks(container)[0]
    expect(root.className).not.toContain('block-arrival')
    // The layout is untouched: reduced motion removes the entrance, not the Stack.
    expect(root.className).toContain('gap-4')
  })
})
