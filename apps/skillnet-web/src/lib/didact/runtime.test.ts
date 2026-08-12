import { describe, expect, it } from 'vitest'

import { resolveDidactMount, withoutProtectedAnswerKeys } from './runtime'

describe('Didact mount runtime', () => {
  it('derives ready, degraded and blocked from registry, policy and ports', () => {
    expect(resolveDidactMount('didact.timeline-steps', {}).availability.status).toBe('ready')
    expect(resolveDidactMount('didact.flashcard', {}).availability.status).toBe('degraded')
    expect(resolveDidactMount('didact.quiz.single-choice', {}).availability.status).toBe('blocked')
  })

  it('blocks unknown components instead of attempting an arbitrary import', () => {
    const result = resolveDidactMount('didact.unknown', {})

    expect(result.policy).toBeUndefined()
    expect(result.availability.status).toBe('blocked')
    expect(result.availability.rendererAvailable).toBe(false)
  })

  it('removes answer keys recursively without mutating other authoring data', () => {
    const input = {
      prompt: 'Choose one',
      answerKey: 'secret',
      items: [{ id: 'a', correctOptionId: 'a', label: 'Visible' }],
      feedback: { expected_answer: 'secret', explanation: 'Visible after evaluation' },
    }

    expect(withoutProtectedAnswerKeys(input)).toEqual({
      prompt: 'Choose one',
      items: [{ id: 'a', label: 'Visible' }],
      feedback: { explanation: 'Visible after evaluation' },
    })
    expect(input.answerKey).toBe('secret')
  })
})
