import type { Meta } from '@storybook/react-vite'
import { Mascota } from './Mascota'

const meta: Meta<typeof Mascota> = {
  title: 'Brand/Mascota',
  component: Mascota,
  parameters: { a11y: { test: 'error' } },
}
export default meta

// Idle: gentle float + the ojos-feliz pop looping (open eyes -> happy smile -> hold -> return).
export const Idle = () => (
  <div className="flex items-center justify-center p-10">
    <Mascota size={220} />
  </div>
)

// Happy held: the smiling eyes stay, only the float continues. For "celebration" moments.
export const Feliz = () => (
  <div className="flex items-center justify-center p-10">
    <Mascota size={220} expression="happy" />
  </div>
)

// Size sweep — check the rig stays crisp small (nav/header) and large (welcome hero).
export const Tamaños = () => (
  <div className="flex flex-wrap items-end gap-10 p-10">
    <Mascota size={64} />
    <Mascota size={120} />
    <Mascota size={200} />
  </div>
)

// On the brand welcome gradient, to preview it in context (light + dark via the toolbar).
export const SobreFondoMarca = () => (
  <div className="setup-welcome-bg flex min-h-[60vh] items-center justify-center rounded-xl p-10">
    <Mascota size={240} />
  </div>
)
