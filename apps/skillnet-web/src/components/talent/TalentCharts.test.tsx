import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { IntlProvider } from 'react-intl'
import { EnrollmentDistributionChart } from './EnrollmentDistributionChart'
import { CourseProgressChart } from './CourseProgressChart'

function renderChart(component: ReactNode) {
  return render(<IntlProvider locale="es">{component}</IntlProvider>)
}

describe('talent charts', () => {
  it('explains enrollment distribution without relying on color', () => {
    renderChart(<EnrollmentDistributionChart assigned={10} inProgress={3} completed={4} />)

    expect(screen.getByText('Sin iniciar')).toBeInTheDocument()
    expect(screen.getByText('En curso')).toBeInTheDocument()
    expect(screen.getByText('Completadas')).toBeInTheDocument()
    expect(screen.getByRole('img')).toHaveAccessibleName('10 matrículas: 3 sin iniciar, 3 en curso y 4 completadas')
  })

  it('shows factual completion ratios per course', () => {
    renderChart(<CourseProgressChart courses={[{
      course_id: 'course-1',
      title: 'Servicio de sala',
      assigned_count: 8,
      in_progress_count: 2,
      completed_count: 4,
      skills: [],
    }]} />)

    expect(screen.getByText('Servicio de sala')).toBeInTheDocument()
    expect(screen.getByText('4/8')).toBeInTheDocument()
    expect(screen.getByRole('img')).toHaveAccessibleName('Servicio de sala: 50% completado, 25% en curso')
  })
})
