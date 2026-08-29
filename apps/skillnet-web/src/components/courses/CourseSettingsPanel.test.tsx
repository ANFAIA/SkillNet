/**
 * The per-course settings panel, exercised on the control this feature added:
 * `image_source_policy`.
 *
 * The three network hooks are replaced rather than backed by a QueryClient — the panel's
 * own logic (optimistic local state, one PUT per change) is what is under test, not
 * TanStack Query.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { CourseSettingsPanel } from './CourseSettingsPanel'
import { es } from '../../i18n/es'
import type { CourseRead, ImageSourcePolicy, NavigationMode } from '../../types'

const mutate = vi.fn()

vi.mock('../../api/courses', async () => {
  const actual = await vi.importActual<typeof import('../../api/courses')>('../../api/courses')
  return { ...actual, useUpdateCourse: () => ({ mutate, isPending: false }) }
})

vi.mock('../../api/users', async () => {
  const actual = await vi.importActual<typeof import('../../api/users')>('../../api/users')
  return { ...actual, useUsers: () => ({ data: { items: [], total: 0 } }) }
})

vi.mock('../../api/enrollments', async () => {
  const actual = await vi.importActual<typeof import('../../api/enrollments')>(
    '../../api/enrollments',
  )
  return {
    ...actual,
    useEnrollments: () => ({ data: { items: [], total: 0 } }),
    useAssignCourse: () => ({ mutate: vi.fn(), isPending: false }),
    useDeleteEnrollment: () => ({ mutate: vi.fn(), isPending: false }),
  }
})

function course(overrides: Partial<CourseRead> = {}): CourseRead {
  return {
    id: 'c1',
    title: 'Devoluciones',
    description: null,
    outcome: null,
    status: 'published',
    source_document_id: 'doc-3',
    created_at: '2026-08-01T00:00:00Z',
    module_count: 2,
    node_count: 6,
    schema_status: 'validated',
    delivery_mode: 'dynamic',
    ...overrides,
  } as CourseRead
}

const option = (label: string) => screen.getByRole('radio', { name: new RegExp(label) })

describe('<CourseSettingsPanel> — image source policy', () => {
  beforeEach(() => mutate.mockClear())

  it('offers the three options, each with the line that says what it does', () => {
    render(<CourseSettingsPanel course={course()} />)

    expect(screen.getByText(es['courseSettings.imagesTitle'])).toBeInTheDocument()
    for (const [label, hint] of [
      ['courseSettings.imagesAuto', 'courseSettings.imagesAutoHint'],
      ['courseSettings.imagesKeep', 'courseSettings.imagesKeepHint'],
      ['courseSettings.imagesRebuild', 'courseSettings.imagesRebuildHint'],
    ] as const) {
      expect(screen.getByText(es[label])).toBeInTheDocument()
      expect(screen.getByText(es[hint])).toBeInTheDocument()
    }
    // Scoped to this control: the panel holds more than one radio group now.
    expect(document.querySelectorAll('input[name="image-source-policy-c1"]')).toHaveLength(3)
  })

  it('defaults to auto when the course carries no policy yet', () => {
    render(<CourseSettingsPanel course={course({ image_source_policy: undefined })} />)
    expect(option(es['courseSettings.imagesAuto'])).toBeChecked()
  })

  it('reflects the stored policy', () => {
    render(<CourseSettingsPanel course={course({ image_source_policy: 'rebuild' })} />)
    expect(option(es['courseSettings.imagesRebuild'])).toBeChecked()
    expect(option(es['courseSettings.imagesAuto'])).not.toBeChecked()
  })

  it.each([
    ['courseSettings.imagesKeep', 'keep_original'],
    ['courseSettings.imagesRebuild', 'rebuild'],
  ] as const)('sends %s as the chosen policy', async (label, expected: ImageSourcePolicy) => {
    const user = userEvent.setup()
    render(<CourseSettingsPanel course={course()} />)

    await user.click(option(es[label]))

    expect(mutate).toHaveBeenCalledWith({
      id: 'c1',
      payload: { image_source_policy: expected },
    })
    // The override is saved on its own: it must not drag the generation permission with it.
    expect(mutate).toHaveBeenCalledTimes(1)
    expect(option(es[label])).toBeChecked()
  })

  it('goes back to auto', async () => {
    const user = userEvent.setup()
    render(<CourseSettingsPanel course={course({ image_source_policy: 'keep_original' })} />)

    await user.click(option(es['courseSettings.imagesAuto']))

    expect(mutate).toHaveBeenCalledWith({ id: 'c1', payload: { image_source_policy: 'auto' } })
  })
})

/**
 * The navigation mode, edited the way `tutor_style` is: one field on the course, one PUT
 * from this panel, no new endpoint.
 *
 * What it does NOT do is decide anything about a lesson. The setting travels to the
 * server and comes back as `LearningNode.available` per node; the panel never computes
 * availability, which is the mistake the padlocks made.
 */
describe('<CourseSettingsPanel> — navigation mode', () => {
  beforeEach(() => mutate.mockClear())

  const mode = (label: string) => screen.getByRole('radio', { name: new RegExp(label) })

  it('offers both modes, each with the line that says what it means', () => {
    render(<CourseSettingsPanel course={course()} />)

    expect(screen.getByText(es['courseSettings.navigationTitle'])).toBeInTheDocument()
    for (const [label, hint] of [
      ['courseSettings.navigationFree', 'courseSettings.navigationFreeHint'],
      ['courseSettings.navigationSequential', 'courseSettings.navigationSequentialHint'],
    ] as const) {
      expect(screen.getByText(es[label])).toBeInTheDocument()
      expect(screen.getByText(es[hint])).toBeInTheDocument()
    }
    expect(document.querySelectorAll('input[name="navigation-mode-c1"]')).toHaveLength(2)
  })

  it('defaults to free for a course made before the column existed', () => {
    render(<CourseSettingsPanel course={course({ navigation_mode: undefined })} />)
    expect(mode(es['courseSettings.navigationFree'])).toBeChecked()
  })

  it('reflects the stored mode', () => {
    render(<CourseSettingsPanel course={course({ navigation_mode: 'sequential' })} />)
    expect(mode(es['courseSettings.navigationSequential'])).toBeChecked()
    expect(mode(es['courseSettings.navigationFree'])).not.toBeChecked()
  })

  it.each([
    ['courseSettings.navigationSequential', 'sequential'],
    ['courseSettings.navigationFree', 'free'],
  ] as const)('sends %s on its own', async (label, expected: NavigationMode) => {
    const user = userEvent.setup()
    const stored: NavigationMode = expected === 'free' ? 'sequential' : 'free'
    render(<CourseSettingsPanel course={course({ navigation_mode: stored })} />)

    await user.click(mode(es[label]))

    expect(mutate).toHaveBeenCalledWith({ id: 'c1', payload: { navigation_mode: expected } })
    // One field per PUT: it must not drag the image policy or the permission with it.
    expect(mutate).toHaveBeenCalledTimes(1)
    expect(mode(es[label])).toBeChecked()
  })
})
