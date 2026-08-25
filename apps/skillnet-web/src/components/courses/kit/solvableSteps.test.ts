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

    expect(conSolve).toEqual(['DragOrderBlock.tsx', 'QuizItemBlock.tsx'])
    expect([...SOLVABLE_COMPONENTS].sort()).toEqual(['DragOrder', 'QuizItem'])
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
