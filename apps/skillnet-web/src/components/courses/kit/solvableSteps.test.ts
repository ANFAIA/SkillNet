/**
 * Que un paso lleve ejercicio se sabe leyendo el programa, no esperando a que el bloque
 * se monte. Esto prueba las dos mitades de esa afirmacion: el recorrido del arbol, y que
 * la lista de componentes que lo cierran no se separe de los bloques que lo abren.
 */

import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

import { SOLVABLE_COMPONENTS, hasSolvableItem, splitMixedScreens } from './solvableSteps'

const here = dirname(fileURLToPath(import.meta.url))
const BLOCKS_DIR = join(here, '..', 'blocks')

/** Un `ElementNode` como lo entrega el parser, con lo justo que mira el recorrido. */
function el(typeName: string, props: Record<string, unknown> = {}) {
  return { type: 'element' as const, typeName, props, partial: false }
}

describe('hasSolvableItem', () => {
  it('no ve ejercicio donde no lo hay', () => {
    expect(hasSolvableItem(el('TextContent', { text: 'hola' }))).toBe(false)
    expect(hasSolvableItem(null)).toBe(false)
    expect(hasSolvableItem('QuizItem')).toBe(false)
  })

  it('reconoce el ejercicio suelto', () => {
    expect(hasSolvableItem(el('QuizItem', { item_id: 'q1' }))).toBe(true)
    expect(hasSolvableItem(el('DragOrder', {}))).toBe(true)
  })

  it('lo encuentra anidado, que es como llega de verdad', () => {
    const card = el('Card', { title: 'Practica', children: [el('QuizItem', {})] })
    expect(hasSolvableItem(card)).toBe(true)

    const stack = el('Stack', { children: [el('TextContent', {}), card], gap: 'md' })
    expect(hasSolvableItem(stack)).toBe(true)
  })

  it('acepta una lista de hijos', () => {
    expect(hasSolvableItem([el('TextContent', {}), el('QuizItem', {})])).toBe(true)
    expect(hasSolvableItem([el('TextContent', {}), el('Callout', {})])).toBe(false)
  })

  it('no se cuelga con un ciclo ni recorre dos veces el mismo nodo', () => {
    const hijo: Record<string, unknown> = el('Card', { title: 'c', children: [] })
    ;(hijo.props as Record<string, unknown>).children = [hijo]
    expect(hasSolvableItem(hijo)).toBe(false)
  })
})

describe('SOLVABLE_COMPONENTS', () => {
  /**
   * La alarma de deriva.
   *
   * El stepper cierra el paso por el NOMBRE del componente y lo abre por la LLAMADA del
   * bloque. Si alguien añade `useStepperSolve()` a un bloque nuevo y no toca la lista,
   * ese ejercicio se puede saltar sin resolverlo; si lo quita de uno que sigue en la
   * lista, el paso no lo abre nadie y el aprendiz se queda encerrado. Ninguna de las dos
   * cosas la ve ningun otro test, porque las dos son coherentes en su propio fichero.
   */
  it('es exactamente el conjunto de bloques que avisan de haberse resuelto', () => {
    const conSolve = readdirSync(BLOCKS_DIR)
      .filter((file) => file.endsWith('.tsx') && !file.includes('.test.') && !file.includes('.stories.'))
      .filter((file) => readFileSync(join(BLOCKS_DIR, file), 'utf8').includes('useStepperSolve()'))
      .sort()

    // Three blocks and two names, and that is not a discrepancy: `SecureEvaluatedActivity`
    // is not a kit component — it is reached through a `LearningExperience`'s
    // `implementation_ref` — so its half of the list is the `usesSecureEvaluationAdapter`
    // rule, checked right below.
    expect(conSolve).toEqual([
      'DragOrderBlock.tsx',
      'QuizItemBlock.tsx',
      'SecureEvaluatedActivity.tsx',
    ])
    expect([...SOLVABLE_COMPONENTS].sort()).toEqual(['DragOrder', 'QuizItem'])
  })

  /**
   * The other half of the mirror.
   *
   * `SecureEvaluatedActivity` calls `useStepperSolve()`, so the step holding it has to be
   * born closed; and the only way to recognise it from the program is the
   * `implementation_ref`, because every experience is emitted under the same name.
   */
  it('cierra el paso de una experiencia que se corrige contra el servidor', () => {
    const evalua = el('LearningExperience', {
      experience_id: 'e1',
      implementation_ref: 'didact.sort@1',
      definition_ref: 'd1',
    })
    const apoyo = el('LearningExperience', {
      experience_id: 'e2',
      implementation_ref: 'didact.flashcard@1',
      definition_ref: 'd2',
    })

    expect(hasSolvableItem(evalua)).toBe(true)
    // A supporting experience checks nothing, so it closes nothing: throwing it in would
    // leave the learner waiting for a correct answer nobody is going to ask them for.
    expect(hasSolvableItem(apoyo)).toBe(false)
    // Nested, which is how it actually arrives.
    expect(hasSolvableItem(el('Card', { title: 'Practica', children: [evalua] }))).toBe(true)
  })
})

/**
 * La pantalla que explicaba y preguntaba a la vez.
 *
 * Reportado desde el producto: la prueba salia en la misma pagina que el concepto. El
 * stepper ya separa por hijo de la raiz, asi que la unica forma de colarse era que el
 * ejercicio viajase DENTRO del mismo hijo que su explicacion, en un `Stack` anidado.
 */
describe('splitMixedScreens', () => {
  const texto = el('TextContent', { text: 'la merma es lo que se pierde' })
  const tabla = el('Table', { headers: [], rows: [] })
  const quiz = el('QuizItem', { item_id: 'q1' })

  it('parte el hijo que mezcla explicacion y ejercicio', () => {
    const mezclado = el('Stack', { children: [texto, quiz], gap: 'md' })
    expect(splitMixedScreens([mezclado])).toEqual([texto, quiz])
  })

  it('deja intacto un hijo que solo explica', () => {
    const soloContenido = el('Stack', { children: [texto, tabla], gap: 'md' })
    expect(splitMixedScreens([soloContenido])).toEqual([soloContenido])
  })

  it('no toca un ejercicio que ya venia solo en su hijo', () => {
    expect(splitMixedScreens([texto, quiz])).toEqual([texto, quiz])
  })

  it('nunca desarma un Card: agrupar con borde lo decidio el generador', () => {
    const card = el('Card', { title: 'Practica', children: [texto, quiz] })
    expect(splitMixedScreens([card])).toEqual([card])
  })

  it('baja tantos niveles como haga falta', () => {
    const dentro = el('Stack', { children: [tabla, quiz], gap: 'sm' })
    const fuera = el('Stack', { children: [texto, dentro], gap: 'md' })
    expect(splitMixedScreens([fuera])).toEqual([texto, tabla, quiz])
  })

  it('conserva todo el contenido: partir no puede perder un bloque', () => {
    const mezclado = el('Stack', { children: [texto, tabla, quiz], gap: 'md' })
    expect(splitMixedScreens([mezclado])).toHaveLength(3)
  })
})

/**
 * La evaluacion que de verdad genera el pipeline.
 *
 * Medido sobre un curso recien generado (2026-08-26): la pantalla de comprobacion no era
 * un `QuizItem`, era `LearningExperience("...", "didact.quiz.multi-select@1", "...")`. Si
 * el partidor solo mira `QuizItem`/`DragOrder`, la evaluacion real vuelve a compartir
 * pantalla con la explicacion sin que nadie se entere.
 */
describe('splitMixedScreens y la evaluacion de las experiencias didact', () => {
  const texto = el('TextContent', { text: 'el concepto' })
  const quizExperiencia = el('LearningExperience', {
    experience_id: 'e1',
    implementation_ref: 'didact.quiz.multi-select@1',
    definition_ref: 'd1',
  })
  const apoyo = el('LearningExperience', {
    experience_id: 'e2',
    implementation_ref: 'didact.flashcard@1',
    definition_ref: 'd2',
  })

  it('separa la experiencia que evalua de la explicacion', () => {
    const mezclado = el('Stack', { children: [texto, quizExperiencia], gap: 'md' })
    expect(splitMixedScreens([mezclado])).toEqual([texto, quizExperiencia])
  })

  it('no separa una experiencia de apoyo, que no comprueba nada', () => {
    const juntos = el('Stack', { children: [texto, apoyo], gap: 'md' })
    expect(splitMixedScreens([juntos])).toEqual([juntos])
  })

  it('reconoce el ref con y sin version', () => {
    const sinVersion = el('LearningExperience', {
      experience_id: 'e3',
      implementation_ref: 'didact.matching',
      definition_ref: 'd3',
    })
    const mezclado = el('Stack', { children: [texto, sinVersion], gap: 'md' })
    expect(splitMixedScreens([mezclado])).toEqual([texto, sinVersion])
  })

  /**
   * The line moved, and it is worth saying why.
   *
   * Until 2026-08-28 this experience split the screen but did NOT close the step: the only
   * way out of `SecureEvaluatedActivity` was a correct answer, so closing a step with one
   * inside meant locking the learner in. There is a way out now — the server sends
   * `show_worked_solution`, the activity hands over the solution and opens the step — so it
   * closes the step like any other exercise.
   *
   * What still cannot happen is `LearningExperience` entering the list BY NAME: half the
   * experiences evaluate nothing.
   */
  it('cierra el paso, ahora que la actividad sabe salir de el', () => {
    expect(hasSolvableItem(quizExperiencia)).toBe(true)
    expect(hasSolvableItem(apoyo)).toBe(false)
    expect(SOLVABLE_COMPONENTS).not.toContain('LearningExperience')
  })
})
