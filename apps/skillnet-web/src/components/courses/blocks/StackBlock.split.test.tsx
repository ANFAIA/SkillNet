import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { IntlProvider } from 'react-intl'
import type { ReactNode } from 'react'

import { StackBlock, StackItem } from './StackBlock'
import { nextNodeContext, stepperContext } from './StepperContext'
import { es as messages } from '../../../i18n/es'

/**
 * "Una idea por pantalla": un bloque PRESENTACIONAL (una Table) y el EJERCICIO nunca
 * comparten pantalla. Es la invariante que rompio el trabajo de variedad de evaluacion
 * (el ejercicio dejaba de cerrar su propia pantalla), y este test la fija desde el lado
 * que de verdad parte las pantallas: la agrupacion del stepper por la etiqueta `solvable`
 * del `StackItem` (ver `kit/solvableSteps.ts` y `StackBlock.tsx`).
 *
 * Se reproduce el nodo real del informe: lead + Table + Callout de contenido, y al final
 * un ejercicio. Los tres presentacionales se agrupan en UNA pantalla; el ejercicio se
 * queda SOLO en la siguiente. La Table no puede aparecer en la pantalla del ejercicio.
 */
function Escenario({ children }: { children: ReactNode }) {
  return (
    <IntlProvider locale="es" messages={messages}>
      <nextNodeContext.Provider value={{ navigate: () => {}, title: 'Nodo 2' }}>
        <stepperContext.Provider value={true}>
          <StackBlock gap="md">{children}</StackBlock>
        </stepperContext.Provider>
      </nextNodeContext.Provider>
    </IntlProvider>
  )
}

/** Una tabla presentacional cualquiera: lo que importa es que NO es `solvable`. */
function Tabla() {
  return (
    <table>
      <tbody>
        <tr>
          <td>Cereales con gluten</td>
        </tr>
      </tbody>
    </table>
  )
}

/** Los cuatro bloques del nodo real: tres presentacionales y, al final, el ejercicio. */
function nodo() {
  return [
    <StackItem key="lead">
      <p>gancho del nodo</p>
    </StackItem>,
    <StackItem key="tabla">
      <Tabla />
    </StackItem>,
    <StackItem key="callout">
      <p>aviso importante</p>
    </StackItem>,
    <StackItem key="ejercicio" solvable>
      <p>el ejercicio</p>
    </StackItem>,
  ]
}

const siguiente = () => screen.getByLabelText(/siguiente/i)

describe('una idea por pantalla: la tabla y el ejercicio no comparten pantalla', () => {
  it('agrupa los presentacionales en una pantalla y deja el ejercicio en la suya', async () => {
    render(<Escenario>{nodo()}</Escenario>)

    // Pantalla 1: los tres bloques presentacionales, juntos. El ejercicio NO esta aqui.
    expect(screen.getByText('gancho del nodo')).toBeInTheDocument()
    expect(screen.getByText('Cereales con gluten')).toBeInTheDocument()
    expect(screen.getByText('aviso importante')).toBeInTheDocument()
    expect(screen.queryByText('el ejercicio')).toBeNull()

    // Pantalla 2: solo el ejercicio. La tabla (y el resto del contenido) ya no estan.
    await userEvent.click(siguiente())
    expect(await screen.findByText('el ejercicio')).toBeInTheDocument()
    expect(screen.queryByText('Cereales con gluten')).toBeNull()
    expect(screen.queryByText('gancho del nodo')).toBeNull()
    expect(screen.queryByText('aviso importante')).toBeNull()
  })
})
