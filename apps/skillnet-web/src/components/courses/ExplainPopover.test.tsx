/**
 * The glimpse popover (§8.4).
 *
 * The word-click glimpse is PLAIN TEXT: one sentence needs no OpenUI kit, and rendering
 * it through the block runtime made it read as an oversized "lead". So this pins that the
 * bubble shows the streamed sentence as ordinary text, renders no `data-ui-format` blocks,
 * and never leaks `root = Stack(...)` dialect even if the server were to send a `ui` event.
 * The rich, block-based view is the job of the "Ver mas" modal, not the glimpse.
 */

import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ExplainPopover } from './ExplainPopover'
import type { ExplainSelection } from './ClickableSurface'

const mockFetch = vi.fn()

/** An SSE body: token (plain text), then done. */
function sse(events: string[]) {
  const encoder = new TextEncoder()
  let index = 0
  return Promise.resolve({
    ok: true,
    status: 200,
    body: {
      getReader: () => ({
        read: () =>
          index < events.length
            ? Promise.resolve({ done: false, value: encoder.encode(events[index++]) })
            : Promise.resolve({ done: true, value: undefined }),
      }),
    },
  })
}

function stream({ text, program }: { text: string; program?: string }) {
  const events = [`event: token\ndata: ${JSON.stringify({ content: text })}\n\n`]
  // The real endpoint no longer emits `ui`; a test may still push one to prove the
  // glimpse ignores it and never shows dialect.
  if (program !== undefined) {
    events.push(`event: ui\ndata: ${JSON.stringify({ program, format: 'explanation' })}\n\n`)
  }
  events.push(
    `event: done\ndata: ${JSON.stringify({ explanation: text, cached: false })}\n\n`,
  )
  return sse(events)
}

function selection(): ExplainSelection {
  const el = document.createElement('span')
  el.textContent = 'merma'
  document.body.appendChild(el)
  return { term: 'merma', context: 'Controlar la merma.', el, range: null, block: el, viaKeyboard: false }
}

function renderPopover() {
  return render(<ExplainPopover selection={selection()} onClose={vi.fn()} />)
}

const GLOSS = 'La merma es el producto que se pierde.'

beforeEach(() => {
  vi.stubGlobal('fetch', mockFetch)
})

afterEach(() => {
  vi.restoreAllMocks()
  mockFetch.mockReset()
})

describe('ExplainPopover — plain-text glimpse', () => {
  it('shows the streamed sentence as plain text, with no OpenUI blocks', async () => {
    mockFetch.mockImplementation(() => stream({ text: GLOSS }))

    renderPopover()

    await screen.findByText(GLOSS)
    expect(document.querySelector('[data-ui-format]')).toBeNull()
  })

  it('ignores a stray ui event and never leaks DSL', async () => {
    // Even if a `ui` program arrived, the glimpse must stay plain text and never paint the
    // dialect as visible text.
    mockFetch.mockImplementation(() =>
      stream({ text: GLOSS, program: 'root = Stack([a])\na = TextContent("hola", "lead")' }),
    )

    renderPopover()

    await screen.findByText(GLOSS)
    expect(document.querySelector('[data-ui-format]')).toBeNull()
    expect(document.body.textContent).not.toContain('root = Stack')
  })
})
