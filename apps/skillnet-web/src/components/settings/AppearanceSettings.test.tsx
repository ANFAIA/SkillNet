import { beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { IntlProvider } from 'react-intl'
import { es } from '../../i18n/es'
import { usePreferences } from '../../stores/preferences'
import { DEFAULT_CUSTOM_ACCENT } from '../../lib/accent-themes'
import { AppearanceSettings } from './AppearanceSettings'

function renderSettings() {
  return render(
    <IntlProvider locale="es" messages={es}>
      <AppearanceSettings />
    </IntlProvider>,
  )
}

beforeEach(() => {
  usePreferences.setState({
    theme: 'system',
    accentColor: 'blue',
    customAccent: DEFAULT_CUSTOM_ACCENT,
    uiPreset: 'clean',
  })
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.removeAttribute('data-accent')
  document.documentElement.style.removeProperty('--custom-accent')
  document.documentElement.removeAttribute('data-ui-preset')
})

describe('AppearanceSettings', () => {
  it('offers system, light and dark color modes', async () => {
    renderSettings()

    await userEvent.click(screen.getByRole('radio', { name: 'Oscuro' }))

    expect(usePreferences.getState().theme).toBe('dark')
    await waitFor(() => {
      expect(document.documentElement.dataset.theme).toBe('dark')
    })
  })

  it('applies a preset accent color independently from the color mode', async () => {
    renderSettings()

    await userEvent.click(screen.getByRole('radio', { name: 'Morado' }))

    expect(usePreferences.getState().accentColor).toBe('purple')
    expect(usePreferences.getState().theme).toBe('system')
    await waitFor(() => {
      expect(document.documentElement.dataset.accent).toBe('purple')
    })
  })

  it('persists a custom accent from the native color picker', async () => {
    renderSettings()
    const picker = screen.getByLabelText('Color personalizado')

    fireEvent.change(picker, { target: { value: '#5f3dc4' } })

    expect(usePreferences.getState().accentColor).toBe('custom')
    expect(usePreferences.getState().customAccent).toBe('#5f3dc4')
    await waitFor(() => {
      expect(document.documentElement.style.getPropertyValue('--custom-accent')).toBe('#5f3dc4')
    })
  })
})
