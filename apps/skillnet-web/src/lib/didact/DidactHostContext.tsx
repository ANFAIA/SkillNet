import { createContext, useContext, type ReactNode } from 'react'

import type { DidactHostPorts } from './host-ports'

const DidactHostContext = createContext<DidactHostPorts | null>(null)

export function DidactHostProvider({
  children,
  ports,
}: {
  children: ReactNode
  ports: DidactHostPorts
}) {
  return <DidactHostContext.Provider value={ports}>{children}</DidactHostContext.Provider>
}

export function useDidactHost(): DidactHostPorts {
  const ports = useContext(DidactHostContext)
  if (!ports) throw new Error('useDidactHost must be used inside DidactHostProvider')
  return ports
}

/** Host adapters may inspect capabilities without requiring a provider in previews. */
export function useOptionalDidactHost(): DidactHostPorts {
  return useContext(DidactHostContext) ?? {}
}
