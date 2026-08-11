import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { IntlProvider } from 'react-intl'
import type { ReactNode } from 'react'

import { StackBlock, StackItem } from './StackBlock'
import {
  courseIntroContext,
  nextNodeContext,
  stepperContext,
  useStepperSolve,
  type CourseIntro,
} from './StepperContext'
import { es as messages } from '../../../i18n/es'

/**
 * Regresion de "acierto el test y me lo vuelve a pedir".
 *
 * En el primer nodo de un curso nuevo, NodeView antepone una diapositiva de intro como
 * pantalla 0 del stepper. Al responder un ejercicio se invalida la lista de nodos (el
 * mastery ha subido), NodeView recalcula `courseIntro` y, al dejar de ser el aprendiz de
 * progreso cero, lo pasa a `null`. Si el stepper leyera ese cambio en vivo, la pantalla 0
 * desapareceria a mitad de leccion: todos los indices bajarian uno, el paso recien resuelto
 * dejaria de coincidir con `solvedStep`, se volveria a cerrar y el ejercicio se remontaria
 * sin respuesta — obligando a repetirlo.
 *
 * Aqui se reproduce ese momento exacto: se resuelve el ejercicio con la intro presente y
 * luego se retira la intro (re-render del padre, como haria la invalidacion). El ejercicio
 * debe seguir resuelto y NO volver a cerrarse.
 */
function EjercicioFalso({ resuelto }: { resuelto: boolean }) {
  const solve = useStepperSolve()
  return (
    <div>
      <p>ejercicio</p>
      <button type="button" onClick={() => solve?.()} disabled={!resuelto}>
        acertar
      </button>
    </div>
  )
}

const irAlSiguienteNodo = vi.fn()

const INTRO: CourseIntro = {
  title: 'Curso de prueba',
  subtitle: '2 nodos · 10 min',
  outcomes: ['Aprender esto', 'Aprender lo otro'],
  buddyMessage: 'Hola',
}

function Escenario({ intro, children }: { intro: CourseIntro | null; children: ReactNode }) {
  return (
    <IntlProvider locale="es" messages={messages}>
      <courseIntroContext.Provider value={intro}>
        <nextNodeContext.Provider value={{ navigate: irAlSiguienteNodo, title: 'Nodo 2' }}>
          <stepperContext.Provider value={true}>
            <StackBlock gap="md">{children}</StackBlock>
          </stepperContext.Provider>
        </nextNodeContext.Provider>
      </courseIntroContext.Provider>
    </IntlProvider>
  )
}

function pasos() {
  return [
    <StackItem key="texto">
      <p>primer bloque</p>
    </StackItem>,
    <StackItem key="ejercicio" solvable>
      <EjercicioFalso resuelto />
    </StackItem>,
  ]
}

const siguiente = () => screen.getByLabelText(/siguiente/i)
const ctaSiguienteNodo = () => screen.queryByRole('button', { name: 'Siguiente: Nodo 2' })

describe('la intro no descoloca el paso resuelto', () => {
  it('mantiene el ejercicio resuelto cuando la intro desaparece tras acertar', async () => {
    const { rerender } = render(<Escenario intro={INTRO}>{pasos()}</Escenario>)

    // Pantalla 0 es la intro del curso.
    expect(screen.getByText('Curso de prueba')).toBeInTheDocument()

    // Avanzar: intro -> texto -> ejercicio.
    await userEvent.click(siguiente())
    await screen.findByText('primer bloque')
    await userEvent.click(siguiente())
    await screen.findByText('ejercicio')

    // El paso nace cerrado; resolver el ejercicio lo abre.
    expect(siguiente()).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'acertar' }))
    expect(siguiente()).not.toBeDisabled()
    expect(ctaSiguienteNodo()).toBeInTheDocument()

    // La invalidacion de la lista de nodos hace que NodeView deje de ofrecer la intro:
    // se re-renderiza el padre con `courseIntro` a null. El stepper NO debe reaccionar.
    rerender(<Escenario intro={null}>{pasos()}</Escenario>)

    // El ejercicio sigue en pantalla, resuelto, sin volver a cerrarse ni remontarse.
    expect(screen.getByText('ejercicio')).toBeInTheDocument()
    expect(siguiente()).not.toBeDisabled()
    expect(ctaSiguienteNodo()).toBeInTheDocument()
  })
})
