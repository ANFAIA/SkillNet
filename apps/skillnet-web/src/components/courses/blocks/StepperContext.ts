import { createContext, useContext } from 'react'
import type { Resultado } from '../feedback/ResultGlow'

/**
 * When true, the root StackBlock renders its children one at a time (Brilliant-style)
 * instead of as a vertical scroll. Only activated in the learner's NodeView.
 */
export const stepperContext = createContext(false)

export function useStepper(): boolean {
  return useContext(stepperContext)
}

/**
 * Aviso de que el ejercicio del paso actual ya esta resuelto.
 *
 * El stepper NO pregunta a los bloques si hay que cerrar el paso: eso ya lo sabe antes
 * de pintar, porque `StackItem` viene etiquetado con si el paso lleva un ejercicio
 * dentro (ver `kit/solvableSteps.ts`). Un paso con ejercicio nace cerrado y esta unica
 * llamada es lo unico que lo abre.
 *
 * Esa direccion —cerrado por defecto, abierto solo por un acierto— es lo que hace el
 * parpadeo imposible: el boton de nodo siguiente nunca puede aparecer y retirarse,
 * porque la transicion contraria (abierto → cerrado dentro del mismo paso) no existe.
 * La version anterior de esto era una compuerta imperativa (`block()` al montar,
 * `unblock()` al acertar) y tenia el defecto inverso: el paso nacia abierto y se cerraba
 * un efecto —o una animacion de salida entera— mas tarde.
 *
 * `null` fuera del stepper (vista de admin, Storybook, tests): ahi los bloques se
 * pintan sueltos y no hay ningun paso que abrir.
 */
export const stepperSolveContext = createContext<(() => void) | null>(null)

export function useStepperSolve(): (() => void) | null {
  return useContext(stepperSolveContext)
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

/**
 * Paginación de un EPISODIO multipantalla.
 *
 * Un episodio ya no es una sola pantalla: cada hijo directo del Stack raíz es una
 * PANTALLA que el aprendiz pasa una a una. A diferencia del stepper legacy, avanzar NUNCA
 * se bloquea (el ejercicio registra su resultado, pero el aprendiz siempre puede seguir).
 *
 * NodeView es el dueño del índice de pantalla (`screen`) y del pie ("Siguiente" avanza de
 * pantalla; en la última avanza de nodo). El StackBlock raíz solo hace dos cosas: informa
 * cuántas pantallas hay (`reportTotal`) y pinta la pantalla `screen`. Cuando el contexto
 * es `null` no hay paginación de episodio (modo legacy o fuera de la lección), así que un
 * Stack anidado dentro de una pantalla se pinta entero.
 */
export interface EpisodePager {
  screen: number
  reportTotal: (total: number) => void
}

export const episodePagerContext = createContext<EpisodePager | null>(null)

export function useEpisodePager(): EpisodePager | null {
  return useContext(episodePagerContext)
}

/**
 * Feedback de la lección: un bloque interactivo (QuizItem, DragOrder) cuenta lo que
 * ha pasado —acertó, falló, casi— y NodeView lo traduce a respuesta ambiental: el
 * `ResultGlow` en el borde y la reacción de la mascota (celebra / ups). El bloque no
 * sabe nada de luces ni de arañas; solo dice una de tres palabras. `definitivo` marca
 * el fallo sin reintento (se acabaron los intentos). `null` fuera de la lección.
 */
export interface LessonFeedback {
  report: (result: Resultado, opts?: { definitivo?: boolean }) => void
}

export const lessonFeedbackContext = createContext<LessonFeedback | null>(null)

export function useLessonFeedback(): LessonFeedback | null {
  return useContext(lessonFeedbackContext)
}

/**
 * Terminar el curso: se llama al pulsar el CTA del último paso del último nodo
 * (cuando ya no hay siguiente). NodeView lo traduce a la pantalla de celebración
 * de fin de curso. `null` fuera de la lección o si no es el último nodo.
 */
export const courseFinishContext = createContext<(() => void) | null>(null)

export function useCourseFinish(): (() => void) | null {
  return useContext(courseFinishContext)
}
