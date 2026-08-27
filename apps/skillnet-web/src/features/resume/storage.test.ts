import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import {
  NODE_POSITION_STORAGE_KEY,
  clearCoursePositions,
  clearNodePosition,
  readNodePosition,
  writeNodePosition,
} from './storage'

const COURSE = 'course-1'
const OTHER_COURSE = 'course-2'
const NODE = 'node-1'

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  vi.restoreAllMocks()
  window.localStorage.clear()
})

describe('node position storage', () => {
  it('remembers a screen and the start gate per (course, node)', () => {
    writeNodePosition(COURSE, NODE, { screen: 3, entered: true })

    expect(readNodePosition(COURSE, NODE)).toEqual({ screen: 3, entered: true })
    // Same node id under another course is a different bookmark.
    expect(readNodePosition(OTHER_COURSE, NODE)).toBeNull()
    expect(readNodePosition(COURSE, 'node-2')).toBeNull()
  })

  it('merges a partial write over what is already stored', () => {
    writeNodePosition(COURSE, NODE, { screen: 2, entered: true })
    writeNodePosition(COURSE, NODE, { screen: 4 })

    expect(readNodePosition(COURSE, NODE)).toEqual({ screen: 4, entered: true })
  })

  it('forgets one node, and a whole course at once', () => {
    writeNodePosition(COURSE, NODE, { screen: 1, entered: true })
    writeNodePosition(COURSE, 'node-2', { screen: 2, entered: true })
    writeNodePosition(OTHER_COURSE, NODE, { screen: 5, entered: true })

    clearNodePosition(COURSE, NODE)
    expect(readNodePosition(COURSE, NODE)).toBeNull()
    expect(readNodePosition(COURSE, 'node-2')?.screen).toBe(2)

    clearCoursePositions(COURSE)
    expect(readNodePosition(COURSE, 'node-2')).toBeNull()
    // Finishing one course must not wipe the bookmark of another.
    expect(readNodePosition(OTHER_COURSE, NODE)?.screen).toBe(5)
  })

  it('caps what accumulates instead of growing for the life of the browser profile', () => {
    for (let index = 0; index < 60; index += 1) {
      writeNodePosition(COURSE, `node-${index}`, { screen: index, entered: true })
    }
    const stored = JSON.parse(window.localStorage.getItem(NODE_POSITION_STORAGE_KEY) ?? '{}')
    expect(Object.keys(stored).length).toBeLessThanOrEqual(40)
    // The newest write always survives the trim.
    expect(readNodePosition(COURSE, 'node-59')?.screen).toBe(59)
  })

  it('reads corrupt storage as "no bookmark" rather than throwing', () => {
    window.localStorage.setItem(NODE_POSITION_STORAGE_KEY, 'not json at all')
    expect(readNodePosition(COURSE, NODE)).toBeNull()

    window.localStorage.setItem(NODE_POSITION_STORAGE_KEY, JSON.stringify({ 'course-1:node-1': { s: 'x', e: 1 } }))
    // A garbage screen index must not become `NaN`, which would break the pager.
    expect(readNodePosition(COURSE, NODE)).toEqual({ screen: 0, entered: true })
  })

  it('survives storage that throws on write (private mode, quota)', () => {
    vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError')
    })
    expect(() => writeNodePosition(COURSE, NODE, { screen: 1, entered: true })).not.toThrow()
  })

  it('is a no-op without a course or node id', () => {
    writeNodePosition(undefined, NODE, { screen: 1 })
    writeNodePosition(COURSE, undefined, { screen: 1 })
    expect(window.localStorage.getItem(NODE_POSITION_STORAGE_KEY)).toBeNull()
    expect(readNodePosition(undefined, undefined)).toBeNull()
  })
})
