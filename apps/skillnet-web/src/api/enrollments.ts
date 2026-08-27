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
  /**
   * Distinct people the order landed on, after the server resolved every group.
   *
   * `0` with a non-empty request means the groups were empty or entirely deactivated —
   * which produces the same `created_count: 0` as "everybody already had it", and only
   * this number tells the two apart.
   */
  person_count: number
  /** Group members left out because their account is deactivated. */
  skipped_inactive_count: number
  enrollments: EnrollmentRead[]
  /** True when `enrollments` is only the first page of what was created. */
  enrollments_truncated: boolean
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
 * Assign one course, or one whole folder, to entire groups of people.
 *
 * Same endpoint and same permissions as the two hooks around it; the difference is one
 * field. `group_ids` names the audience and the **server** resolves it to its members —
 * this hook deliberately does not fetch them. With the people list paginated the browser
 * does not know every member of a group, and `user_ids` is capped at 100 anyway, so
 * expanding here would break on exactly the groups worth having.
 *
 * The answer is always the counts shape, never a bare list: assigning to a set of people
 * nobody enumerated has an outcome ("42 of 60 created, 3 inactive skipped") that a list
 * of rows cannot express.
 */
export function useAssignToGroups() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: {
      group_ids: string[]
      user_ids?: string[]
      course_id?: string
      folder_id?: string
      deadline?: string
    }) => post<EnrollmentAssignmentResult>('/enrollments', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['enrollments'] })
      queryClient.invalidateQueries({ queryKey: ['talent'] })
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
