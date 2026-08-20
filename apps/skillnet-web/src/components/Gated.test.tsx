import { render, renderHook, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'

import { Gated } from './Gated'
import { useCapability, type Capabilities, type SetupStatus } from '../api/setup'

/** A client whose setup-status query is pre-seeded with the given capabilities. */
function wrapperWith(capabilities?: Partial<Capabilities>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const status: SetupStatus = { initialized: true }
  if (capabilities) status.capabilities = capabilities as Capabilities
  client.setQueryData(['setup', 'status'], status)
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

describe('<Gated>', () => {
  it('renders children when the capability is present', () => {
    render(
      <Gated requires="tutor">
        <span>tutor chip</span>
      </Gated>,
      { wrapper: wrapperWith({ tutor: true }) },
    )
    expect(screen.getByText('tutor chip')).toBeInTheDocument()
  })

  it('renders nothing (not an error) when the capability is absent', () => {
    render(
      <Gated requires="tutor">
        <span>tutor chip</span>
      </Gated>,
      { wrapper: wrapperWith({ tutor: false }) },
    )
    expect(screen.queryByText('tutor chip')).not.toBeInTheDocument()
  })

  it('renders the fallback when provided and the capability is absent', () => {
    render(
      <Gated requires="images" fallback={<span>connect a key</span>}>
        <span>infographic</span>
      </Gated>,
      { wrapper: wrapperWith({ images: false }) },
    )
    expect(screen.queryByText('infographic')).not.toBeInTheDocument()
    expect(screen.getByText('connect a key')).toBeInTheDocument()
  })
})

describe('useCapability', () => {
  it('defaults to available (safe) when the field is missing', () => {
    const { result } = renderHook(() => useCapability('generation'), {
      wrapper: wrapperWith(undefined),
    })
    expect(result.current).toBe(true)
  })

  it('reflects an explicit false', () => {
    const { result } = renderHook(() => useCapability('generation'), {
      wrapper: wrapperWith({ generation: false }),
    })
    expect(result.current).toBe(false)
  })
})
