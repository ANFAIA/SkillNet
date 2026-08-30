/**
 * The URL of a course, asked for from wherever the learner happens to be.
 *
 * The case that matters is "from inside a lesson". The map panel lives on both screens,
 * and the code it replaced rebuilt the course URL by trimming the current one, which is
 * only the course when the course is what you are looking at. From a lesson it appended a
 * second `/nodo/` segment, no route matched, and the catch-all in `App.tsx` sent the
 * learner to their dashboard — a bug that reads as "the menu takes me home".
 */
import { describe, expect, it } from 'vitest'

import { coursePath, isAdminPreviewPath, nodePath } from './courseRoutes'

describe('coursePath', () => {
  it('answers the same URL from the course and from inside one of its lessons', () => {
    expect(coursePath('/empleado/curso/c1', 'c1')).toBe('/empleado/curso/c1')
    expect(coursePath('/empleado/curso/c1/nodo/n7', 'c1')).toBe('/empleado/curso/c1')
  })

  it('stays on the admin test drive when that is the screen in hand', () => {
    expect(coursePath('/admin/probar-curso/c1', 'c1')).toBe('/admin/probar-curso/c1')
    expect(coursePath('/admin/probar-curso/c1/nodo/n7', 'c1')).toBe('/admin/probar-curso/c1')
  })

  it('takes the course id from the caller, not from the URL', () => {
    // The learner is reading c1 and the list is pointing at a different course. Trimming
    // the current URL would have produced a link into c1 wearing c2's node id.
    expect(coursePath('/empleado/curso/c1/nodo/n7', 'c2')).toBe('/empleado/curso/c2')
  })

  it('ignores a trailing slash', () => {
    expect(coursePath('/empleado/curso/c1/', 'c1')).toBe('/empleado/curso/c1')
  })

  it('falls back to the learner screen when the location is neither', () => {
    // Somewhere sensible beats a URL that exists nowhere: this is still the right course.
    expect(coursePath('/admin/contenido', 'c1')).toBe('/empleado/curso/c1')
    expect(coursePath('/', 'c1')).toBe('/empleado/curso/c1')
  })
})

describe('nodePath', () => {
  it('hangs the lesson off the course, once', () => {
    expect(nodePath('/empleado/curso/c1', 'n7')).toBe('/empleado/curso/c1/nodo/n7')
    expect(nodePath('/admin/probar-curso/c1', 'n7')).toBe('/admin/probar-curso/c1/nodo/n7')
  })
})

describe('isAdminPreviewPath', () => {
  it('tells the admin test drive from the learner screen, at any depth', () => {
    expect(isAdminPreviewPath('/admin/probar-curso/c1')).toBe(true)
    expect(isAdminPreviewPath('/admin/probar-curso/c1/nodo/n7')).toBe(true)
    expect(isAdminPreviewPath('/empleado/curso/c1/nodo/n7')).toBe(false)
    // The admin's own course screens are not the test drive.
    expect(isAdminPreviewPath('/admin/curso/c1')).toBe(false)
  })
})
