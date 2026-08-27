import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post } from './client'
import type { EnrollmentRead, Paginated } from '../types'

export interface EnrollmentFilters {
  status?: string
  user_id?: string
  course_id?: string
}

function toQuery(filters?: EnrollmentFilters): string {
  if (!filters) return ''
  const params = new URLSearchParams()
  if (filters.status) params.set('status', filters.status)
  if (filters.user_id) params.set('user_id', filters.user_id)
  if (filters.course_id) params.set('course_id', filters.course_id)
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

export function useEnrollments(filters?: EnrollmentFilters) {
  return useQuery({
    queryKey: ['enrollments', filters ?? {}],
    queryFn: () => get<Paginated<EnrollmentRead>>(`/enrollments${toQuery(filters)}`),
    staleTime: 30_000,
  })
}

export function useEnrollment(id: string | undefined) {
  return useQuery({
    queryKey: ['enrollments', id],
    queryFn: () => get<EnrollmentRead>(`/enrollments/${id}`),
    enabled: !!id,
  })
}

/**
 * What `POST /enrollments` answers when the order names a *folder*.
 *
 * The single-course branch still answers with a bare `EnrollmentRead[]`, so
 * `useAssignCourse` below is byte-for-byte the call it always was. A folder cannot:
 * it is a set of courses, assigning it is idempotent, and "3 of 8 created, 5 already
 * there" is the outcome the screen has to say out loud.
 */
export interface EnrollmentAssignmentResult {
  /** Published courses the folder held. `0` means the assignment enrolled nobody. */
  course_count: number
  created_count: number
  skipped_existing_count: number
  enrollments: EnrollmentRead[]
}

export function useAssignCourse() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: { user_ids: string[]; course_id: string; deadline?: string }) =>
      post<EnrollmentRead[]>('/enrollments', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['enrollments'] })
    },
  })
}

/**
 * Assign every published course of one folder to these people.
 *
 * Same endpoint and same permissions as `useAssignCourse` — one field of the body
 * differs — so the employee record does not need a second contract to know about. The
 * other direction of the same operation (folder -> many people, from the library) is
 * `useAssignCourseFolder` in `api/course-folders.ts`.
 */
export function useAssignFolder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: { user_ids: string[]; folder_id: string; deadline?: string }) =>
      post<EnrollmentAssignmentResult>('/enrollments', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['enrollments'] })
      // The talent screens count assigned training per person.
      queryClient.invalidateQueries({ queryKey: ['talent'] })
    },
  })
}

export function useDeleteEnrollment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (enrollmentId: string) => del(`/enrollments/${enrollmentId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['enrollments'] })
    },
  })
}

export function useCompleteEnrollment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (enrollmentId: string) =>
      post<EnrollmentRead>(`/enrollments/${enrollmentId}/complete`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['enrollments'] })
    },
  })
}
