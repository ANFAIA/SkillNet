import { useMutation, useQuery } from '@tanstack/react-query'

import { writtenSolution } from './activity-ports'
import type { DidactValue, EvaluationSolution } from '../lib/didact/host-ports'
import type { PublicActivityDefinition } from '../types/didact-activity'
import { get, post } from './client'

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

/**
 * Where a Didact activity asks for its next hint.
 *
 * A path and not a request, because the request belongs to `HintLadder`: the ladder owns
 * the escalation and the server owns the count, and the only thing this family needed to
 * contribute was the URL. `POST` here answers with a `NodeHintResult` — the same shape
 * `/nodes/{id}/hint` returns, which is what lets one ladder serve both.
 */
export const activityHintPath = (activityId: string) =>
  `/activities/${encodeURIComponent(activityId)}/hint`

/**
 * The learner asking to see the solution, instead of waiting for the fourth failure to
 * hand it over.
 *
 * The answer may legitimately be **nothing**: the server does not know how to write out
 * every evaluation mode, and it says so by sending no solution rather than by failing.
 * `null` here means "asked and answered, there is nothing to print" — which the caller
 * has to tell apart from "not asked yet", because it still closes the activity and still
 * has to let the learner move on.
 */
export function useActivitySolution(activityId: string) {
  return useMutation({
    mutationFn: async (): Promise<EvaluationSolution | null> => {
      const response = await post<DidactValue>(
        `/activities/${encodeURIComponent(activityId)}/solution`,
        {},
      )
      return writtenSolution(response) ?? null
    },
  })
}
