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
 * Whether this learner has already been shown the worked solution of this activity.
 *
 * Server-owned, and that is the point. The reveal used to live only in component state,
 * so a reload put the activity back on the screen as if it were still open — ready to be
 * answered by somebody who had already read the answer. The flag rides next to the
 * client-owned state blob rather than inside it, so writing state back cannot un-reveal
 * it.
 *
 * Defaults to `false` while loading and on error: showing a closed activity as open is
 * recoverable (the learner answers, the server decides), showing an open one as closed is
 * not.
 */
export const activityRevealKey = (activityId: string) =>
  ['activities', activityId, 'solution-revealed'] as const

function useActivityServerState(activityId: string) {
  return useQuery({
    queryKey: activityRevealKey(activityId),
    queryFn: () =>
      get<{ solution_revealed?: boolean; failures?: number }>(
        `/activities/${encodeURIComponent(activityId)}/state`,
      ),
    staleTime: 5 * 60 * 1000,
    retry: false,
    refetchOnWindowFocus: false,
  })
}

export function useActivitySolutionRevealed(activityId: string) {
  return useActivityServerState(activityId).data?.solution_revealed === true
}

/**
 * How many graded attempts this learner has already failed on this activity.
 *
 * Read by the block that decides whether the help is on screen yet. Defaults to `0` while
 * loading and on error, which errs towards *not* offering the answer to somebody who has
 * not tried — the opposite bias to `useActivitySolutionRevealed`, and for the same reason:
 * each default is the recoverable one for what it guards.
 */
export function useActivityFailures(activityId: string) {
  return useActivityServerState(activityId).data?.failures ?? 0
}
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
