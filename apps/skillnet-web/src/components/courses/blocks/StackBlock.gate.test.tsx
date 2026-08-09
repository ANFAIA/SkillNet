import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { IntlProvider } from 'react-intl'
import { useEffect } from 'react'
import type { ReactNode } from 'react'

import { StackBlock } from './StackBlock'
import { nextNodeContext, stepperContext, useStepperGate } from './StepperContext'
import { messages } from '../../../i18n/es'

/**
 * La compuerta, sin el quiz de por medio.
 *
 * `QuizItemBlock` arrastra react-query, el POST de respuesta y el contexto de render;
 * un doble que hace lo mismo —cerrar al montarse, abrir al resolverse— prueba el
 * mecanismo sin nada de eso.
 *
 * Hay un nodo siguiente en todos los casos **a proposito**: sin el, el chevron del
 * ultimo paso esta deshabilitado por no tener a donde ir, y el test pasaria sin que la
 * compuerta hiciera nada.
 */
function EjercicioFalso({ resuelto }: { resuelto: boolean }) {
  const gate = useStepperGate()
  useEffect(() => {
    if (resuelto) gate?.unblock()
    else gate?.block()
  }, [gate, resuelto])
  return <p>ejercicio</p>
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

const siguiente = () => screen.getByLabelText(/siguiente/i)

describe('la compuerta del stepper', () => {
  it('deja avanzar mientras no hay ejercicio en pantalla', async () => {
    render(
      <Escenario>
        <p>primer bloque</p>
        <EjercicioFalso resuelto={false} />
      </Escenario>,
    )
    expect(siguiente()).not.toBeDisabled()
    await userEvent.click(siguiente())
    // `AnimatePresence mode="wait"` desmonta antes de montar: hay que esperar.
    expect(await screen.findByText('ejercicio')).toBeInTheDocument()
  })

  it('cierra el paso mientras el ejercicio esta sin resolver', async () => {
    render(
      <Escenario>
        <p>primer bloque</p>
        <EjercicioFalso resuelto={false} />
      </Escenario>,
    )
    await userEvent.click(siguiente())
    await screen.findByText('ejercicio')
    // `waitFor` y no un `expect` seco: el bloqueo lo pide el efecto del ejercicio, que
    // corre despues de pintarlo. Hay un frame en que ya se ve y todavia se puede pulsar.
    await waitFor(() => expect(siguiente()).toBeDisabled())

    await userEvent.click(siguiente(), { pointerEventsCheck: 0 })
    expect(irAlSiguienteNodo).not.toHaveBeenCalled()
  })

  it('lo abre cuando el ejercicio se resuelve', async () => {
    const { rerender } = render(
      <Escenario>
        <p>primer bloque</p>
        <EjercicioFalso resuelto={false} />
      </Escenario>,
    )
    await userEvent.click(siguiente())
    await screen.findByText('ejercicio')
    await waitFor(() => expect(siguiente()).toBeDisabled())

    rerender(
      <Escenario>
        <p>primer bloque</p>
        <EjercicioFalso resuelto={true} />
      </Escenario>,
    )
    expect(siguiente()).not.toBeDisabled()
  })
})
