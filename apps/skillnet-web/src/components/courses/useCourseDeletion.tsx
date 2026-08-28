import { useState } from 'react'
import { useIntl } from 'react-intl'
import { ApiError } from '../../api/client'
import { useDeleteCourse } from '../../api/courses'
import { fetchCourseDeletionImpact, type CourseDeletionImpact } from '../../api/enrollments'
import type { CourseRead } from '../../types'
import { CourseDeleteDialog } from './CourseDeleteDialog'

/** A failure, and the course it belongs to, so a list can show it on the right row. */
export interface CourseDeletionError {
  courseId: string
  message: string
}

interface UseCourseDeletionOptions {
  /** Run after the course is gone — refresh a list, or leave a page that now 404s. */
  onDeleted?: (course: CourseRead) => void
}

/**
 * Delete a course, warned in proportion to what the delete destroys.
 *
 * The server no longer refuses anything — any course, any status, enrollments included —
 * so the judgement lives here, and it cannot be made without the numbers. Two reads of a
 * single row answer it: how many people hold this course, and how many finished it.
 *
 * - Nobody finished it: a `window.confirm` naming the scope, like the rest of the admin
 *   area. What is lost is the admin's own work.
 * - Somebody finished it: `CourseDeleteDialog`, which says the exact counts and asks for
 *   the course title to be typed back. That is somebody else's record of training, and
 *   there is no undo for it.
 *
 * If the counts cannot be read, nothing is deleted. Guessing low is the one wrong answer
 * available here: it would silently downgrade the second case into the first.
 *
 * A hook and not a copy in each screen, because the library and the course preview both
 * offer the delete and the warning has to be the same in both. A safeguard that depends
 * on which button you reached the action from is not a safeguard.
 */
export function useCourseDeletion({ onDeleted }: UseCourseDeletionOptions = {}) {
  const intl = useIntl()
  const deleteCourse = useDeleteCourse()
  const [heavy, setHeavy] = useState<{ course: CourseRead; impact: CourseDeletionImpact } | null>(null)
  const [error, setError] = useState<CourseDeletionError | null>(null)

  async function run(course: CourseRead) {
    try {
      await deleteCourse.mutateAsync(course.id)
      setHeavy(null)
      onDeleted?.(course)
    } catch (reason) {
      // A 409 means something still points at the course with a restrictive foreign key.
      // English on the wire, so it is translated rather than shown. The dialog, when
      // there is one, stays open so the answer lands where the button was.
      setError({
        courseId: course.id,
        message: reason instanceof ApiError && reason.status === 409
          ? intl.formatMessage({ id: 'content.courseDeleteBlocked' })
          : intl.formatMessage({ id: 'content.courseDeleteError' }),
      })
    }
  }

  async function requestDelete(course: CourseRead) {
    setError(null)
    let impact: CourseDeletionImpact
    try {
      impact = await fetchCourseDeletionImpact(course.id)
    } catch {
      setError({ courseId: course.id, message: intl.formatMessage({ id: 'content.courseDeleteImpactError' }) })
      return
    }
    if (impact.completed > 0) {
      setHeavy({ course, impact })
      return
    }
    const message = impact.total > 0
      ? intl.formatMessage({ id: 'content.courseDeleteConfirmEnrolled' }, { title: course.title, count: impact.total })
      : intl.formatMessage({ id: 'content.courseDeleteConfirm' }, { title: course.title })
    if (!window.confirm(message)) return
    await run(course)
  }

  return {
    requestDelete,
    error,
    clearError: () => setError(null),
    /** True only for the row being deleted, so one spinner does not disable a whole list. */
    isDeleting: (courseId: string) => deleteCourse.isPending && deleteCourse.variables === courseId,
    /** Render this somewhere in the tree; it is `null` unless the heavy case came up. */
    dialog: heavy ? (
      <CourseDeleteDialog
        course={heavy.course}
        impact={heavy.impact}
        deleting={deleteCourse.isPending}
        error={error?.courseId === heavy.course.id ? error.message : null}
        onConfirm={() => run(heavy.course)}
        onClose={() => { setHeavy(null); setError(null) }}
      />
    ) : null,
    /** The course the dialog is about, when it is open. */
    pendingCourse: heavy?.course ?? null,
  }
}
