import { useQuery } from '@tanstack/react-query'
import { get } from './client'
import type { StatsResponse } from '../types'

export function useStats() {
  return useQuery({
    queryKey: ['stats'],
    queryFn: () => get<StatsResponse>('/stats'),
  })
}
