import { describe, expect, it } from 'vitest'
import { formatSkillName } from './formatSkillName'

describe('formatSkillName', () => {
  it('turns stored slugs into readable labels', () => {
    expect(formatSkillName('gestion_de_alergenos')).toBe('Gestion de alergenos')
    expect(formatSkillName('atención,_límites_y_falsa_multitarea')).toBe('Atención, límites y falsa multitarea')
  })

  it('keeps already readable labels stable', () => {
    expect(formatSkillName('Resolver incidencias de acceso')).toBe('Resolver incidencias de acceso')
  })
})
