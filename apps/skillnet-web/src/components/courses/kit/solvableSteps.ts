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
  const solvable = kids.filter((kid) => hasSolvableItem(kid)).length
  return solvable > 0 && solvable < kids.length ? kids : null
}
