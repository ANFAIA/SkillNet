import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from './client'
import type { AttemptRead, AttemptResult, CorrectResult, ExerciseAnswer } from '../types'

export function useSubmitAttempt() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ exerciseId, answer }: { exerciseId: string; answer: ExerciseAnswer }) =>
      post<AttemptResult>(`/exercises/${exerciseId}/attempt`, { answer }),
    onSettled: () => {
      // Score comes from the server — refresh anything that depends on it.
      queryClient.invalidateQueries({ queryKey: ['enrollments'] })
      queryClient.invalidateQueries({ queryKey: ['courses'] })
    },
  })
}

export function useCorrectExercise() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (exerciseId: string) =>
      post<CorrectResult>(`/exercises/${exerciseId}/correct`),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['enrollments'] })
      queryClient.invalidateQueries({ queryKey: ['courses'] })
    },
  })
}

export function useExerciseAttempts(exerciseId: string | undefined) {
  return useQuery({
    queryKey: ['exercises', exerciseId, 'attempts'],
    queryFn: () => get<AttemptRead[]>(`/exercises/${exerciseId}/attempts`),
    enabled: !!exerciseId,
  })
}
