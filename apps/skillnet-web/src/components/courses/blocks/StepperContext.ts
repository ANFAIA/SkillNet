import { createContext, useContext } from 'react'

/**
 * When true, the root StackBlock renders its children one at a time (Brilliant-style)
 * instead of as a vertical scroll. Only activated in the learner's NodeView.
 */
export const stepperContext = createContext(false)

export function useStepper(): boolean {
  return useContext(stepperContext)
}

/**
 * Callback the stepper provides so interactive blocks (QuizItem, DragOrder)
 * can auto-advance to the next step on successful completion.
 */
export const stepperAdvanceContext = createContext<(() => void) | null>(null)

export function useStepperAdvance(): (() => void) | null {
  return useContext(stepperAdvanceContext)
}

/**
 * Course-level position so the stepper can show node-level dots.
 * Set by NodeView, read by StackBlock's progress indicator.
 */
export interface CoursePosition {
  nodeCount: number
  currentNodeIndex: number
}

export const coursePositionContext = createContext<CoursePosition | null>(null)

export function useCoursePosition(): CoursePosition | null {
  return useContext(coursePositionContext)
}

/**
 * Navigate to the next node when the stepper finishes.
 */
export const nextNodeContext = createContext<(() => void) | null>(null)

export function useNextNode(): (() => void) | null {
  return useContext(nextNodeContext)
}
