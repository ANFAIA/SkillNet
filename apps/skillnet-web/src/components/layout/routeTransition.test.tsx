import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, Outlet, Link } from 'react-router-dom'
import { motion, LayoutGroup } from 'framer-motion'

/**
 * The blank main area on route change.
 *
 * Symptom: clicking "Mis Cursos" sometimes left the whole main area blank — right URL,
 * responsive app, nothing painted — and a second click always fixed it.
 *
 * Root cause: both route layouts wrapped `<Outlet />` in `AnimatePresence mode="wait"`
 * with an exit variant. `Outlet` is not frozen, so the incoming page mounted inside the
 * exiting node. When that page registered a `layoutId`, framer never called
 * `safeToRemove` and the outgoing node lingered at `opacity: 0`.
 *
 * Fix (original): enter-only framer wrapper, no `AnimatePresence`.
 * Fix (current): View Transitions API handles crossfades natively. The layouts use a
 * plain `<div>` around `<Outlet />` — no framer-motion at all for the page wrapper. The
 * structural invariant is stricter: no AnimatePresence, no motion wrapper, no exit phase.
 */

const LAYOUTS = ['AppLayout.tsx', 'AdminLayout.tsx'] as const

/**
 * Source with comments removed. The layouts explain this bug at length in prose, and
 * that prose necessarily names the very constructs these assertions forbid — so match
 * against code only.
 */
function layoutSource(file: string) {
  return readFileSync(resolve(__dirname, file), 'utf8')
    .replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, '') // {/* jsx comment */}
    .replace(/\/\*[\s\S]*?\*\//g, '') // /* block */
    .replace(/^\s*\/\/.*$/gm, '') // // line
}

describe('route transition — blank main area regression', () => {
  describe.each(LAYOUTS)('%s', (file) => {
    it('does not wrap the route Outlet in AnimatePresence', () => {
      const src = layoutSource(file)
      expect(src).toContain('<Outlet />')
      // The precise thing that must never come back. An exit phase around an
      // unfrozen Outlet is what strands the outgoing node at opacity 0.
      expect(src).not.toContain('AnimatePresence')
    })

    it('does not use a framer-motion page wrapper around Outlet', () => {
      const src = layoutSource(file)
      // View Transitions API replaces framer for route-level crossfades. The
      // layout must not re-introduce a motion.div wrapper around the Outlet —
      // that was the other half of the deadlock.
      expect(src).not.toContain('{...pageTransition}')
      expect(src).not.toContain('motion.div')
    })
  })

  /**
   * The behavioural half: a layout shaped like the real ones — plain div around
   * the Outlet, with a `layoutId` on the destination page (the ingredient that
   * triggered the original deadlock). The new page must always end up visible.
   */
  function Layout() {
    return (
      <main>
        <nav>
          <Link to="/">home</Link>
          <Link to="/cursos">cursos</Link>
        </nav>
        <div data-testid="page-wrapper">
          <Outlet />
        </div>
      </main>
    )
  }

  function CoursesPage() {
    return (
      <div>
        <h2>Mis Cursos</h2>
        <LayoutGroup>
          <motion.span layoutId="tab-underline" />
        </LayoutGroup>
      </div>
    )
  }

  it('shows the destination page after navigating', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<h2>Inicio</h2>} />
            <Route path="cursos" element={<CoursesPage />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: 'Inicio' })).toBeInTheDocument()

    await user.click(screen.getByRole('link', { name: 'cursos' }))

    expect(await screen.findByRole('heading', { name: 'Mis Cursos' })).toBeInTheDocument()
  })

  it('renders exactly one page wrapper — the outgoing one is gone in the same commit', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<h2>Inicio</h2>} />
            <Route path="cursos" element={<CoursesPage />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    await user.click(screen.getByRole('link', { name: 'cursos' }))

    expect(screen.getAllByTestId('page-wrapper')).toHaveLength(1)
    expect(screen.queryByRole('heading', { name: 'Inicio' })).not.toBeInTheDocument()
  })
})
