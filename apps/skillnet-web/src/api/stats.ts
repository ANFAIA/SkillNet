import { useQuery } from '@tanstack/react-query'
import { get } from './client'
import type { StatsResponse } from '../types'

export function useStats(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['stats'],
    queryFn: () => get<StatsResponse>('/stats'),
    // Org-only endpoint: skip it in an individual workspace, where it 404s.
    enabled: options?.enabled ?? true,
  })
}
