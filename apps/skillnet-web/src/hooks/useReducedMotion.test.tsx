import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'

/**
 * The half of "reduced motion" that a media query cannot see.
 *
 * Question 5 of the onboarding wizard offers `reduce_motion` ("Menos animaciones") and
 * stores it in `users.accessibility`. Before this hook existed nothing in the frontend
 * read that column: the OS preference was the only input, so a learner on a locked-down
 * shared laptop — who cannot change an OS setting and therefore ticked the box instead —
 * got the full animation anyway. These tests exist because that failure is silent: every
 * screen still works, it just moves at someone who asked it not to.
 */

/** `framer-motion` returns `null` before it has read the media query, then a boolean. */
let systemPrefers: boolean | null = false

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual<typeof import('framer-motion')>('framer-motion')
  return { ...actual, useReducedMotion: () => systemPrefers }
})

const { declaredReducedMotionContext, useReducedMotion } = await import('./useReducedMotion')

function Probe() {
  return <span data-testid="answer">{String(useReducedMotion())}</span>
}

function withDeclared(declared: boolean, children: ReactNode) {
  return (
    <declaredReducedMotionContext.Provider value={declared}>
      {children}
    </declaredReducedMotionContext.Provider>
  )
}

function answer() {
  return screen.getByTestId('answer').textContent
}

beforeEach(() => {
  systemPrefers = false
})

describe('useReducedMotion', () => {
  it('honours the OS preference with no provider in the tree', () => {
    systemPrefers = true
    render(<Probe />)
    expect(answer()).toBe('true')
  })

  it('honours the learner who declared it in the wizard, with the OS silent', () => {
    systemPrefers = false
    render(withDeclared(true, <Probe />))
    expect(answer()).toBe('true')
  })

  it('never lets one source turn motion back on for the other', () => {
    systemPrefers = true
    render(withDeclared(false, <Probe />))
    expect(answer()).toBe('true')
  })

  it('animates when neither source objects', () => {
    systemPrefers = false
    render(withDeclared(false, <Probe />))
    expect(answer()).toBe('false')
  })

  it('reads the not-yet-measured `null` as "no objection", not as a preference', () => {
    // Outside a browser (and on the first frame) framer answers `null`. Treating that
    // as truthy would silence every animation in Storybook and in every unit test.
    systemPrefers = null
    render(<Probe />)
    expect(answer()).toBe('false')
  })
})
