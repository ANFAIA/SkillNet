import { describe, expect, it } from 'vitest'

import { validateTextContentDefinition } from './text-content-definition'

describe('validateTextContentDefinition', () => {
  it('accepts the reviewed fallback emitted by ExperienceMaterializer', () => {
    expect(validateTextContentDefinition({
      content: '  Aplica la regla antes de decidir.  ',
      variant: 'lead',
    })).toEqual({
      ok: true,
      definition: { content: 'Aplica la regla antes de decidir.', variant: 'lead' },
    })
  })

  it.each([
    null,
    [],
    { content: '', variant: 'lead' },
    { content: 'Texto', variant: 'hero' },
    { content: 'x'.repeat(1_601), variant: 'body' },
  ])('rejects malformed or non-minimal definitions', (definition) => {
    expect(validateTextContentDefinition(definition)).toEqual({ ok: false })
  })
})

