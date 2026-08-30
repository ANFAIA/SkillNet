import { matchPath, useLocation } from 'react-router-dom'

/**
 * The one place that knows what the URL of a course looks like.
 *
 * A course is read from two screens — the learner's and the admin's test drive — and
 * every component inside them used to rebuild the course URL out of the current one by
 * hand. Three copies, three different expressions, and the one in `NodeList` assumed the
 * current URL *was* the course: opened from the panel inside a lesson it produced
 * `/empleado/curso/A/nodo/B/nodo/C`, which matches no route in `App.tsx`, so the
 * catch-all sent the learner home. Clicking a lesson in the course map looked exactly
 * like clicking "Home", which is why it read as a navigation bug and not as a bad link.
 *
 * So nothing here parses the current URL for the course id: the id comes from the data
 * the caller already holds, and the location is asked one question only — which of the
 * two screens are we on. A location that is neither answers the learner's, because that
 * is where a course lives and the admin test drive is the exception. That fallback is a
 * working link to the right course, which is the point: the failure mode of this module
 * is "somewhere sensible", never "a URL that exists nowhere".
 */

/** Every screen a course is read from. Used both to recognise one and to build one. */
const LEARNER_PREFIX = '/empleado/curso'
const ADMIN_PREVIEW_PREFIX = '/admin/probar-curso'
const COURSE_PREFIXES = [LEARNER_PREFIX, ADMIN_PREVIEW_PREFIX] as const

function isUnder(prefix: string, pathname: string): boolean {
  return matchPath({ path: `${prefix}/:id`, end: false }, pathname) !== null
}

/**
 * The course URL, for the screen `pathname` belongs to. Works at any depth: the course
 * itself, one of its lessons, or anything nested deeper added later.
 */
export function coursePath(pathname: string, courseId: string): string {
  const prefix = COURSE_PREFIXES.find((candidate) => isUnder(candidate, pathname)) ?? LEARNER_PREFIX
  return `${prefix}/${courseId}`
}

/**
 * Whether the course is being read from the admin's test drive rather than by a learner.
 * Here and not spelled out again at the call site, because it is the same knowledge the
 * rest of this module keeps: what an admin course URL looks like.
 */
export function isAdminPreviewPath(pathname: string): boolean {
  return isUnder(ADMIN_PREVIEW_PREFIX, pathname)
}

/** `coursePath` for the screen in hand. */
export function useCoursePath(courseId: string): string {
  return coursePath(useLocation().pathname, courseId)
}

/** One lesson of a course. `base` is what `coursePath` / `useCoursePath` returned. */
export function nodePath(base: string, nodeId: string): string {
  return `${base}/nodo/${nodeId}`
}
