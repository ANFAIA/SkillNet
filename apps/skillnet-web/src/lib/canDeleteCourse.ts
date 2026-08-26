import type { CourseRead } from '../types'

/**
 * Whether to offer the delete action for a course.
 *
 * The server is the authority — `DELETE /courses/{id}` refuses anything that is not a
 * draft, and any draft somebody is enrolled in, both with a 409 the screen shows. This is
 * only about not offering a button that is certain to be refused, which is why it stops at
 * what a course listing already knows. The demo course is excluded because it is seeded,
 * not authored: deleting it leaves the org with an empty tour and no way back.
 */
export function canDeleteCourse(course: CourseRead): boolean {
  return course.status === 'draft' && !course.is_demo
}
