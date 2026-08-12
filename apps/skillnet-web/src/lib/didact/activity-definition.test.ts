import { describe, expect, it } from 'vitest'

import { validatePublicActivityDefinition } from './activity-definition'

describe('public Didact activity definitions', () => {
  it('accepts a matching installed component and removes nested answer keys', () => {
    const result = validatePublicActivityDefinition({
      activity_id: 'activity-1',
      component_id: 'didact.quiz.single-choice',
      status: 'ready',
      public_definition: {
        question: 'Choose safely',
        options: [{ id: 'a', label: 'A', correctAnswer: true }],
        answer_key: ['a'],
      },
    }, 'activity-1', 'didact.quiz.single-choice')

    expect(result.ok).toBe(true)
    if (result.ok) {
      expect(result.componentProps).toEqual({
        question: 'Choose safely',
        options: [{ id: 'a', label: 'A' }],
      })
    }
  })

  it('fails closed when the server component does not match OpenUI', () => {
    const result = validatePublicActivityDefinition({
      activity_id: 'activity-1',
      component_id: 'didact.flashcard',
      status: 'ready',
      public_definition: { front: 'Question', back: 'Answer' },
    }, 'activity-1', 'didact.code-exercise')

    expect(result).toEqual({ ok: false, reason: 'component_mismatch' })
  })

  it('preserves an honest declined state', () => {
    const result = validatePublicActivityDefinition({
      activity_id: 'activity-1',
      component_id: 'didact.simulation-lab',
      status: 'declined',
      public_definition: {},
    }, 'activity-1', 'didact.simulation-lab')

    expect(result).toEqual({ ok: false, reason: 'declined' })
  })
})
