import type { CourseRead } from '../types'

/**
 * Whether to offer the delete action for a course.
 *
 * It used to also require a draft, because the server refused anything else. That rule is
 * gone: an admin may delete their own content in any status, enrollments included, and
 * the safeguard is the warning in front of it — the exact numbers, and the course title
 * typed back when somebody has already completed it — plus the `course_deleted` row in
 * `audit_log` that outlives the course.
 *
 * The demo course is still excluded, and for a reason that has nothing to do with status:
 * it is seeded, not authored. Deleting it leaves the organization with an empty tour and
 * no way back.
 */
export function canDeleteCourse(course: CourseRead): boolean {
  return !course.is_demo
}
