import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CourseSkillsEditor, type SkillOption } from './CourseSkillsEditor'

function Harness({ initial = [] }: { initial?: SkillOption[] }) {
  const [skills, setSkills] = useState(initial)
  return (
    <CourseSkillsEditor
      skills={skills}
      availableSkills={[{ id: 'existing', name: 'Validar entradas' }]}
      onChange={setSkills}
    />
  )
}

describe('CourseSkillsEditor', () => {
  it('adds a concrete new skill and lets the creator edit it', async () => {
    const user = userEvent.setup()
    render(<Harness />)

    await user.type(screen.getByLabelText('Nueva habilidad'), 'Resolver incidencias')
    await user.click(screen.getByRole('button', { name: 'Añadir' }))

    const skill = screen.getByLabelText('Habilidad 1')
    expect(skill).toHaveValue('Resolver incidencias')
    await user.clear(skill)
    await user.type(skill, 'Resolver incidencias de acceso')
    await user.tab()
    expect(screen.getByLabelText('Habilidad 1')).toHaveValue('Resolver incidencias de acceso')
  })

  it('reuses an existing skill without duplicating it', async () => {
    const user = userEvent.setup()
    render(<Harness initial={[{ name: 'Resolver incidencias' }]} />)

    await user.click(screen.getByRole('button', { name: '+ Validar entradas' }))
    expect(screen.getByLabelText('Habilidad 2')).toHaveValue('Validar entradas')
    expect(screen.queryByRole('button', { name: '+ Validar entradas' })).toBeNull()
  })
})
