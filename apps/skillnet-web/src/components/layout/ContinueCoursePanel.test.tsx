import { render, screen } from '@testing-library/react'
import { IntlProvider } from 'react-intl'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { EnrollmentRead } from '../../types'
import { ContinueCoursePanel } from './ContinueCoursePanel'

const enrollment: EnrollmentRead = {
  id: 'enrollment-1',
  course_id: 'course-1',
  user_id: 'user-1',
  status: 'in_progress',
  deadline: null,
  score: null,
  progress: 0.42,
  course_title: 'Seguridad de la informacion',
  started_at: null,
  completed_at: null,
  delivery_mode: 'static',
}

describe('ContinueCoursePanel', () => {
  it('links to the real course and exposes its progress', () => {
    render(
      <IntlProvider
        locale="es"
        messages={{
          'nav.continueCourse': 'Continuar curso',
          'nav.courseProgress': 'Progreso del curso: {progress}%',
        }}
      >
        <MemoryRouter>
          <ContinueCoursePanel enrollment={enrollment} onNavigate={vi.fn()} />
        </MemoryRouter>
      </IntlProvider>,
    )

    expect(screen.getByRole('link')).toHaveAttribute('href', '/empleado/curso/course-1')
    expect(screen.getByText('Seguridad de la informacion')).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Progreso del curso: 42%' })).toHaveValue(42)
  })
})
