import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { IntlProvider } from '../../i18n/IntlProvider'
import { Modal } from './Modal'

/**
 * The motion itself is not asserted here (jsdom has no layout). These pin what must hold
 * whatever the animation does: it is a labelled dialog, it closes on Escape and on the close
 * button, and it leaves the page once closed. Reduced motion is forced so mounting and
 * unmounting are immediate and the test does not wait on a timer.
 */
vi.mock('../../hooks/useReducedMotion', () => ({ useReducedMotion: () => true }))

function renderModal(props: Partial<React.ComponentProps<typeof Modal>> = {}) {
  const onClose = vi.fn()
  const view = render(
    <IntlProvider>
      <Modal open onClose={onClose} {...props}>
        <p>Contenido de la ventana</p>
      </Modal>
    </IntlProvider>,
  )
  return { onClose, ...view }
}

describe('Modal', () => {
  it('shows its content inside a modal dialog', () => {
    renderModal()
    expect(screen.getByRole('dialog')).toHaveAttribute('aria-modal', 'true')
    expect(screen.getByText('Contenido de la ventana')).toBeInTheDocument()
  })

  it('closes on Escape', async () => {
    const { onClose } = renderModal()
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('closes from the close button, and the button can be hidden', async () => {
    const { onClose, rerender } = renderModal()
    await userEvent.click(screen.getByRole('button'))
    expect(onClose).toHaveBeenCalledTimes(1)

    rerender(
      <IntlProvider>
        <Modal open onClose={onClose} hideClose>
          <p>Contenido de la ventana</p>
        </Modal>
      </IntlProvider>,
    )
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('leaves the page when it closes and locks scrolling while it is open', () => {
    const { rerender } = renderModal()
    expect(document.body.style.overflow).toBe('hidden')

    rerender(
      <IntlProvider>
        <Modal open={false} onClose={() => {}}>
          <p>Contenido de la ventana</p>
        </Modal>
      </IntlProvider>,
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(document.body.style.overflow).not.toBe('hidden')
  })

  it('opens with an origin rect without failing', () => {
    renderModal({ origin: new DOMRect(10, 10, 120, 36), size: 'lg' })
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})
