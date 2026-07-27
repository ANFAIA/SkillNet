import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, Outlet, Link, useLocation } from 'react-router-dom'
import { motion, LayoutGroup } from 'framer-motion'
import { pageTransition } from '../../lib/motion'

/**
 * The blank main area on route change.
 *
 * Symptom: clicking "Mis Cursos" sometimes left the whole main area blank — right URL,
 * responsive app, nothing painted — and a second click always fixed it.
 *
 * Cause: both route layouts wrapped `<Outlet />` in `AnimatePresence mode="wait"` with
 * an exit variant. `Outlet` is not frozen, so while the outgoing element stayed mounted
 * to play its 200 ms exit, React re-rendered its subtree against the *new* location and
 * the incoming page mounted **inside the node that was exiting**. When that page
 * registered a `layoutId` from in there — `MyCourses` has a `LayoutGroup` tab underline
 * and was the only employee page that did — framer never called `safeToRemove` for the
 * exiting key, so the incoming child was never swapped in and the exiting node was left
 * at its exit end-state, `opacity: 0`, holding the new page's DOM.
 *
 * Fix: the layouts are enter-only. No `AnimatePresence`, so no exit phase and nothing
 * that has to report completion.
 *
 * Honesty about coverage: the deadlock itself is a real-browser, production-build
 * timing bug — it does not reproduce under jsdom (nor under the Vite dev server), so no
 * unit test can *provoke* it. It was reproduced and the fix verified with Playwright
 * against the production bundle: 4/16 plain navigations and 12/12 rapid-click sequences
 * blanked before, 0/28 after. What these tests pin is the invariant that makes the
 * deadlock impossible, so it cannot be reintroduced by editing the layouts.
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

    it('does not spread the exit variant onto the page wrapper', () => {
      const src = layoutSource(file)
      // `{...pageTransition}` would pull in `exit`, which is only safe for an
      // AnimatePresence with stable children.
      expect(src).not.toContain('{...pageTransition}')
      expect(src).toContain('initial={pageTransition.initial}')
      expect(src).toContain('animate={pageTransition.animate}')
    })
  })

  /**
   * The behavioural half: a layout shaped exactly like the real ones, with a
   * `layoutId` on the destination page — the ingredient that triggered the deadlock.
   * The new page must end up in the document *and* fully visible.
   */
  function Layout() {
    const location = useLocation()
    return (
      <main>
        <nav>
          <Link to="/">home</Link>
          <Link to="/cursos">cursos</Link>
        </nav>
        <motion.div
          key={location.pathname}
          initial={pageTransition.initial}
          animate={pageTransition.animate}
          data-testid="page-wrapper"
        >
          <Outlet />
        </motion.div>
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

  it('shows the destination page, visible, after navigating', async () => {
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
    // The failure was never "no heading" — it was a heading nobody could see.
    await waitFor(() => {
      expect(screen.getByTestId('page-wrapper')).toHaveStyle({ opacity: '1' })
    })
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

    // With `mode="wait"` the outgoing wrapper lingers for the length of the exit;
    // without an exit phase the swap is a single commit and there is only ever one.
    expect(screen.getAllByTestId('page-wrapper')).toHaveLength(1)
    expect(screen.queryByRole('heading', { name: 'Inicio' })).not.toBeInTheDocument()
  })
})
