import type { Meta } from '@storybook/react-vite'
import { Logo } from './Logo'

const meta: Meta<typeof Logo> = {
  title: 'Brand/Logo',
  component: Logo,
  parameters: { a11y: { test: 'error' } },
}
export default meta

// Accent — follows the user's chosen accent via var(--color-primary).
export const Accent = () => (
  <div className="flex items-center justify-center p-10">
    <Logo tone="accent" size={96} />
  </div>
)

// On a dark ground the mark is forced white so it reads.
export const OnDark = () => (
  <div className="flex items-center justify-center rounded-xl bg-zinc-900 p-10">
    <Logo tone="on-dark" size={96} />
  </div>
)

// On a light ground the mark is a dark brand neutral.
export const OnLight = () => (
  <div className="flex items-center justify-center rounded-xl bg-white p-10">
    <Logo tone="on-light" size={96} />
  </div>
)

// Size sweep — check the mark stays crisp small (nav/header) and large (hero).
export const Tamaños = () => (
  <div className="flex flex-wrap items-end gap-8 p-10">
    <Logo size={24} />
    <Logo size={48} />
    <Logo size={96} />
  </div>
)
