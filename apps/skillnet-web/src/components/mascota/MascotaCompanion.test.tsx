import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { IntlProvider } from 'react-intl'
import { es } from '../../i18n/es'
import { usePreferences } from '../../stores/preferences'
import { MascotaCompanion } from './MascotaCompanion'

// A paginated episode: each root-Stack child is one screen, with its own text.
const EPISODE = [
  'root = Stack([p0, p1], "md")',
  'p0 = Stack([t0], "md")',
  't0 = TextContent("Primera pantalla del episodio.", "lead")',
  'p1 = Stack([t1], "md")',
  't1 = TextContent("Segunda pantalla del episodio.", "body")',
].join('\n')

function renderCompanion(props: Partial<React.ComponentProps<typeof MascotaCompanion>>) {
  return render(
    <IntlProvider locale="es" messages={es}>
      <MascotaCompanion
        nodeId="node-1"
        title="Titulo del nodo"
        summary="Resumen del nodo entero."
        fx={null}
        onOpenChat={() => undefined}
        {...props}
      />
    </IntlProvider>,
  )
}

beforeEach(() => {
  // Muted: the bubble text is shown regardless, and muting keeps the test off the
  // TTS endpoint and the Audio element entirely.
  usePreferences.setState({ mascotaMuted: true, locale: 'es' })
  vi.restoreAllMocks()
})

describe('MascotaCompanion per-page text', () => {
  it("shows the current screen's own text in a paginated episode", () => {
    const { rerender } = renderCompanion({ program: EPISODE, screen: 0 })
    expect(screen.getByRole('status')).toHaveTextContent('Primera pantalla del episodio.')

    // Advancing a page must move the mascot's text to that page.
    rerender(
      <IntlProvider locale="es" messages={es}>
        <MascotaCompanion
          nodeId="node-1"
          title="Titulo del nodo"
          summary="Resumen del nodo entero."
          program={EPISODE}
          screen={1}
          fx={null}
          onOpenChat={() => undefined}
        />
      </IntlProvider>,
    )
    expect(screen.getByRole('status')).toHaveTextContent('Segunda pantalla del episodio.')
  })

  it('falls back to the node summary when there is no episode program (legacy shell)', () => {
    renderCompanion({ program: null, screen: 0 })
    expect(screen.getByRole('status')).toHaveTextContent('Resumen del nodo entero.')
  })
})
