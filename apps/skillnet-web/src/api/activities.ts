import { useQuery } from '@tanstack/react-query'

import type { PublicActivityDefinition } from '../types/didact-activity'
import { get } from './client'

export const activityDefinitionKey = (activityId: string | undefined) =>
  ['activities', activityId, 'definition'] as const

export function useActivityDefinition(activityId: string | undefined) {
  return useQuery({
    queryKey: activityDefinitionKey(activityId),
    queryFn: () => get<PublicActivityDefinition>(`/activities/${encodeURIComponent(activityId ?? '')}/definition`),
    enabled: Boolean(activityId),
    staleTime: 5 * 60 * 1000,
    retry: false,
    refetchOnWindowFocus: false,
  })
}
