import { describe, expect, it } from 'vitest'

import { autolinkBareDomains } from './autolinkBareDomains'

describe('autolinkBareDomains', () => {
  it('wraps a bare domain in markdown link syntax', () => {
    expect(autolinkBareDomains('Entra en events.ticketrona.com y sigue los pasos.')).toBe(
      'Entra en [events.ticketrona.com](https://events.ticketrona.com) y sigue los pasos.',
    )
  })

  it('does not touch an already-linked domain', () => {
    const text = 'Ver el [manual](https://events.ticketrona.com/manual) completo.'
    expect(autolinkBareDomains(text)).toBe(text)
  })

  it('does not false-positive on a filename or step number', () => {
    expect(autolinkBareDomains('Sube el archivo v3.pdf y sigue el paso 2.1 del manual.')).toBe(
      'Sube el archivo v3.pdf y sigue el paso 2.1 del manual.',
    )
  })

  it('leaves plain text with no dot untouched', () => {
    expect(autolinkBareDomains('Sin ningun dominio aqui')).toBe('Sin ningun dominio aqui')
  })
})
