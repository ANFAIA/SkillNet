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

/**
 * Los componentes del kit que cierran el paso hasta acertar.
 *
 * Es el espejo exacto de quien llama a `useStepperSolve()` en `blocks/`, y
 * `solvableSteps.test.ts` falla si uno de los dos lados se mueve sin el otro. Un nombre
 * de menos aqui = un ejercicio que se puede saltar; uno de mas = un aprendiz atascado
 * en un paso que nadie va a abrir.
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
 * True si en `value` —un `ElementNode`, una lista de ellos o cualquier prop— hay un
 * ejercicio, a la profundidad que sea: un `QuizItem` dentro de un `Card` dentro de un
 * `Stack` anidado sigue cerrando el paso que lo contiene.
 *
 * El arbol resuelto es un DAG, no un arbol: el mismo nodo puede colgar de varios sitios
 * y la expansion medida llega a decenas de miles de elementos. De ahi el `seen`, que
 * ademas hace inofensiva cualquier referencia circular que el parser dejara pasar.
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
    return hasSolvableItem(value.props, seen)
  }
  return Object.values(value as Record<string, unknown>).some((entry) => hasSolvableItem(entry, seen))
}
