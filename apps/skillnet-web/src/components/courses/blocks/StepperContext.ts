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
 * Course-level position: which node the learner is on and how many there are.
 * Set by NodeView, available to any component inside the lesson tree.
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
 * Carries the navigation callback and the next node's title so the stepper
 * can render a descriptive CTA ("Siguiente: [title]").
 */
export interface NextNodeInfo {
  navigate: () => void
  title: string
}

export const nextNodeContext = createContext<NextNodeInfo | null>(null)

export function useNextNode(): NextNodeInfo | null {
  return useContext(nextNodeContext)
}

/**
 * Course intro slides to prepend before the node content.
 * Only set for the first node when the learner has no progress.
 */
export interface CourseIntro {
  title: string
  subtitle: string // "X nodos · Y min"
  outcomes: string[] // learning objectives
  buddyMessage: string
}

export const courseIntroContext = createContext<CourseIntro | null>(null)

export function useCourseIntro(): CourseIntro | null {
  return useContext(courseIntroContext)
}

/**
 * Callback that StepperStack calls to report its step progress up to NodeView.
 * NodeView renders the progress dots in its top bar, so it needs this data.
 */
export interface StepperProgress {
  currentStep: number
  totalSteps: number
}

export type StepperProgressCallback = (progress: StepperProgress) => void

export const stepperProgressContext = createContext<StepperProgressCallback | null>(null)

export function useStepperProgressReport(): StepperProgressCallback | null {
  return useContext(stepperProgressContext)
}
