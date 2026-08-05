/**
 * `GET /health` — public health check, read once at startup.
 *
 * `staleTime: Infinity` plus no refetch on focus or mount: the health status is a
 * connectivity check, not something the client should poll for.
 */

import { useQuery } from '@tanstack/react-query'
import { get } from './client'

export interface HealthRead {
  status: string
  version: string
  database: string
}

export const healthKey = ['health'] as const

export function useHealth() {
  return useQuery({
    queryKey: healthKey,
    queryFn: () => get<HealthRead>('/health'),
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
  })
}
