/**
 * Que pasos del stepper exigen resolverse antes de dejar avanzar.
 *
 * La pregunta se responde sobre el programa YA PARSEADO —el arbol de `ElementNode` que
 * el runtime entrega al renderer de `Stack`— y no sobre lo que se acaba pintando. Es la
 * diferencia entre saberlo y enterarse:
 *
 * - Lo que se pinta es `QuizItemRenderer`, que delega en `QuizItemBlock`. Desde el
 *   `Stack` no hay forma honesta de reconocerlo: entre medias esta el envoltorio del
 *   runtime, que es detalle de implementacion de una version fijada del paquete.
 * - Y con `AnimatePresence mode="wait"` el bloque del paso nuevo ni siquiera existe
 *   hasta que termina la animacion de salida del anterior, asi que cualquier respuesta
 *   que dependa de que el bloque se monte llega cientos de milisegundos tarde.
 *
 * `ElementNode` si es modelo de datos publico del parser (`typeName` + `props`), que es
 * lo unico que se toca aqui.
 */

import type { ElementNode } from '@openuidev/react-lang'

import { usesSecureEvaluationAdapter } from '../blocks/secure-evaluation-components'

/**
 * The kit components that close the step, BY NAME.
 *
 * Half a list. The other half cannot be recognised by the element name — every experience
 * is emitted as `LearningExperience` — but by its `implementation_ref`, and that rule
 * lives in `isEvaluativeExperience` below.
 *
 * The two together mirror exactly who calls `useStepperSolve()` in `blocks/`, and
 * `solvableSteps.test.ts` fails if either side moves without the other. One name missing
 * here = an exercise that can be skipped; one name too many = a learner stuck in a step
 * nobody will ever open.
 */
export const SOLVABLE_COMPONENTS: readonly string[] = ['QuizItem', 'DragOrder']

function isElementNode(value: unknown): value is ElementNode {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as { type?: unknown }).type === 'element' &&
    typeof (value as { typeName?: unknown }).typeName === 'string'
  )
}

/**
 * A `LearningExperience` whose implementation is graded against the server.
 *
 * Which components evaluate is not decided here: it is asked of
 * `usesSecureEvaluationAdapter`, which already is the list of the ones graded server-side,
 * and those are exactly the ones `blocks/SecureEvaluatedActivity.tsx` paints. A supporting
 * experience — `didact.flashcard`, a glossary — checks nothing and closes no step.
 */
function isEvaluativeExperience(node: ElementNode): boolean {
  if (node.typeName !== 'LearningExperience') return false
  const ref = (node.props as { implementation_ref?: unknown } | undefined)?.implementation_ref
  // The ref travels versioned (`...@1`); the list is written without a version.
  return typeof ref === 'string' && usesSecureEvaluationAdapter(ref.split('@')[0])
}

/**
 * True when `value` — an `ElementNode`, a list of them, or any prop — holds something that
 * CHECKS what was learnt, at any depth: a `QuizItem` inside a `Card` inside a nested
 * `Stack` still closes the step that contains it.
 *
 * ## Why there is no longer a second function
 *
 * Until 2026-08-28 this lived next to a wider `hasEvaluation` that did count the didact
 * experiences. The gap was not a design nuance: for SPLITTING the screen an experience
 * counted as evaluation, and for CLOSING the step it did not, because the step is opened
 * by whoever calls `useStepperSolve()` and `SecureEvaluatedActivity` did not call it. It
 * could not: it had no way out other than getting the answer right, so closing a step with
 * one of those inside would have locked the learner in.
 *
 * Now it has one — the server sends `show_worked_solution`, the activity hands over the
 * solution and opens the step — so the reason for the distinction is gone and the two
 * functions merged into this one. Four exits hold that up, and every one of them calls
 * solve: a correct answer, the solution handed over, an activity that cannot be graded
 * (`ActivityNotEvaluableError`), and an activity that never even mounted
 * (`useSolveStepWhen` in `LearningExperience` and `DidactActivityBlock`). Lose any of
 * them and the locked-in learner is back.
 *
 * ## The walk
 *
 * The resolved tree is a DAG, not a tree: the same node can hang off several places and
 * the measured expansion reaches tens of thousands of elements. Hence `seen`, which also
 * makes harmless any circular reference the parser might let through.
 */
export function hasSolvableItem(value: unknown, seen: WeakSet<object> = new WeakSet()): boolean {
  if (Array.isArray(value)) {
    return value.some((entry) => hasSolvableItem(entry, seen))
  }
  if (typeof value !== 'object' || value === null) return false
  if (seen.has(value)) return false
  seen.add(value)

  if (isElementNode(value)) {
    if (SOLVABLE_COMPONENTS.includes(value.typeName)) return true
    if (isEvaluativeExperience(value)) return true
    return hasSolvableItem(value.props, seen)
  }
  return Object.values(value as Record<string, unknown>).some((entry) => hasSolvableItem(entry, seen))
}

/**
 * Los hijos de la raiz, con las pantallas que mezclaban explicacion y ejercicio partidas.
 *
 * El stepper ya separa: cada hijo de la raiz que lleve un ejercicio dentro se queda solo en
 * su pantalla (`blocks/StackBlock.tsx`). Lo que no puede separar es un hijo que lleve las
 * DOS cosas — el texto que explica y el `QuizItem` que lo pregunta — dentro de un `Stack`
 * anidado: eso es UN hijo, luego UNA pantalla, y ahi el ejercicio sale con la respuesta
 * escrita justo encima. El prompt ya no lo pide (`runtime/42`), pero los cursos generados
 * antes siguen en la base de datos y hay que servirlos bien.
 *
 * Un `Stack` anidado es solo maquetacion —apila en columna, igual que el de la raiz—, asi
 * que subir sus hijos un nivel no cambia lo que se ve fuera del stepper y dentro convierte
 * la pantalla mezclada en las dos que siempre debio ser. Se hace SOLO cuando mezcla: un
 * `Stack` de puro contenido se queda intacto, y un `Card` NUNCA se toca (agrupar con borde
 * es una decision de diseno del generador, no un contenedor accidental).
 */
export function splitMixedScreens(children: unknown[]): unknown[] {
  const out: unknown[] = []
  for (const child of children) {
    const nested = mixedNestedStackChildren(child)
    if (nested) out.push(...splitMixedScreens(nested))
    else out.push(child)
  }
  return out
}

/**
 * Los hijos de `value` si es un `Stack` anidado que mezcla ejercicio y contenido; `null`
 * en cualquier otro caso.
 */
function mixedNestedStackChildren(value: unknown): unknown[] | null {
  if (!isElementNode(value) || value.typeName !== 'Stack') return null
  const raw = (value.props as { children?: unknown } | undefined)?.children
  const kids = (Array.isArray(raw) ? raw : [raw]).flat().filter((kid) => kid != null)
  if (kids.length < 2) return null
  const evalua = kids.filter((kid) => hasSolvableItem(kid)).length
  return evalua > 0 && evalua < kids.length ? kids : null
}
