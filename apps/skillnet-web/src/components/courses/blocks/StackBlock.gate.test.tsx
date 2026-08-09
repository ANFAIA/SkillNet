import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { IntlProvider } from 'react-intl'
import type { ReactNode } from 'react'

import { StackBlock, StackItem } from './StackBlock'
import { nextNodeContext, stepperContext, useStepperSolve } from './StepperContext'
import { es as messages } from '../../../i18n/es'

/**
 * La compuerta, sin el quiz de por medio.
 *
 * `QuizItemBlock` arrastra react-query, el POST de respuesta y el contexto de render;
 * un doble que hace lo mismo —avisar cuando se resuelve— prueba el mecanismo sin nada
 * de eso. Lo que cierra el paso no es el doble: es la etiqueta `solvable` del
 * `StackItem`, igual que en produccion (ver `kit/solvableSteps.ts`).
 *
 * Hay un nodo siguiente en todos los casos **a proposito**: sin el, el chevron del
 * ultimo paso esta deshabilitado por no tener a donde ir, y el test pasaria sin que la
 * compuerta hiciera nada.
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

function Escenario({ children }: { children: ReactNode }) {
  return (
    <IntlProvider locale="es" messages={messages}>
      <nextNodeContext.Provider value={{ navigate: irAlSiguienteNodo, title: 'Nodo 2' }}>
        <stepperContext.Provider value={true}>
          <StackBlock gap="md">{children}</StackBlock>
        </stepperContext.Provider>
      </nextNodeContext.Provider>
    </IntlProvider>
  )
}

/**
 * Los dos pasos de siempre: uno de texto y, al final, un ejercicio.
 *
 * Una lista y no un fragmento: `Children.toArray` aplana arrays pero NO entra en los
 * fragmentos, asi que un `<>...</>` contaria como un solo paso y el stepper se
 * cortocircuitaria.
 */
function pasos(resuelto = false) {
  return [
    <StackItem key="texto">
      <p>primer bloque</p>
    </StackItem>,
    <StackItem key="ejercicio" solvable>
      <EjercicioFalso resuelto={resuelto} />
    </StackItem>,
  ]
}

const siguiente = () => screen.getByLabelText(/siguiente/i)
const ctaSiguienteNodo = () => screen.queryByRole('button', { name: 'Siguiente: Nodo 2' })

describe('la compuerta del stepper', () => {
  it('deja avanzar mientras no hay ejercicio en pantalla', async () => {
    render(<Escenario>{pasos()}</Escenario>)
    expect(siguiente()).not.toBeDisabled()
    await userEvent.click(siguiente())
    // `AnimatePresence mode="wait"` desmonta antes de montar: hay que esperar.
    expect(await screen.findByText('ejercicio')).toBeInTheDocument()
  })

  it('cierra el paso mientras el ejercicio esta sin resolver', async () => {
    render(<Escenario>{pasos()}</Escenario>)
    await userEvent.click(siguiente())
    // Sin `waitFor`: el paso esta cerrado desde el primer render, no desde el efecto de
    // nadie. Si esto necesitara esperar, el cierre volveria a llegar tarde.
    expect(siguiente()).toBeDisabled()
    await screen.findByText('ejercicio')
    expect(siguiente()).toBeDisabled()

    await userEvent.click(siguiente(), { pointerEventsCheck: 0 })
    expect(irAlSiguienteNodo).not.toHaveBeenCalled()

    // La flecha del teclado es otro camino y tenia su propio agujero: el listener se
    // registraba sin `isGated` en las dependencias y leia un valor congelado.
    await userEvent.keyboard('{ArrowRight}')
    expect(irAlSiguienteNodo).not.toHaveBeenCalled()
    expect(screen.getByText('ejercicio')).toBeInTheDocument()
  })

  it('lo abre cuando el ejercicio se resuelve', async () => {
    render(<Escenario>{pasos(true)}</Escenario>)
    await userEvent.click(siguiente())
    await screen.findByText('ejercicio')
    expect(siguiente()).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: 'acertar' }))
    expect(siguiente()).not.toBeDisabled()
    expect(ctaSiguienteNodo()).toBeInTheDocument()
  })

  it('no enseña el boton de nodo siguiente en la ventana en que el ejercicio aun no ha montado', async () => {
    render(<Escenario>{pasos()}</Escenario>)
    await userEvent.click(siguiente())

    // Aqui el stepper ya esta en el ultimo paso, pero el ejercicio TODAVIA NO EXISTE:
    // `AnimatePresence mode="wait"` no lo monta hasta que termine la salida del bloque
    // anterior. Esa ventana —cientos de milisegundos, no un frame— era el parpadeo, y
    // ningun orden de efectos podia taparla porque no habia hijo que corriera ninguno.
    expect(screen.queryByText('ejercicio')).toBeNull()
    expect(ctaSiguienteNodo()).toBeNull()

    await screen.findByText('ejercicio')
    expect(ctaSiguienteNodo()).toBeNull()
  })

  it('vuelve a cerrar el paso si se sale y se entra otra vez', async () => {
    render(<Escenario>{pasos(true)}</Escenario>)
    await userEvent.click(siguiente())
    await screen.findByText('ejercicio')
    await userEvent.click(screen.getByRole('button', { name: 'acertar' }))
    expect(siguiente()).not.toBeDisabled()

    // Atras y adelante: el ejercicio se monta de cero, sin respuesta, asi que el permiso
    // de salir no puede seguir en pie.
    await userEvent.click(screen.getByLabelText(/paso anterior/i))
    await screen.findByText('primer bloque')
    await userEvent.click(siguiente())
    expect(siguiente()).toBeDisabled()
    expect(ctaSiguienteNodo()).toBeNull()
  })
})
