import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from './client'
import type { EnrollmentRead, Paginated } from '../types'

export interface CourseFolder {
  id: string
  name: string
  course_count?: number
  created_at?: string
  updated_at?: string
}

export interface CourseFolderAssignmentResult {
  course_count: number
  created_count: number
  skipped_existing_count: number
}

export function useCourseFolders() {
  return useQuery({
    queryKey: ['course-folders'],
    queryFn: () => get<CourseFolder[]>('/course-folders'),
  })
}

export function useCreateCourseFolder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => post<CourseFolder>('/course-folders', { name }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['course-folders'] }),
  })
}

export function useRenameCourseFolder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      put<CourseFolder>(`/course-folders/${id}`, { name }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['course-folders'] })
      queryClient.invalidateQueries({ queryKey: ['courses'] })
    },
  })
}

export function useDeleteCourseFolder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => del<void>(`/course-folders/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['course-folders'] })
      queryClient.invalidateQueries({ queryKey: ['courses'] })
    },
  })
}

export interface FolderCourseEnrollments {
  /** How many of the given courses each user is enrolled in, keyed by user id. */
  enrolledCountByUser: Record<string, number>
  /**
   * The enrollment rows themselves, keyed by user id.
   *
   * Taking a folder away from someone needs more than a count: `DELETE /enrollments/{id}`
   * works one enrollment at a time and refuses (409) any row that is not still
   * `assigned`, so the caller has to know each row's id *and* its status before it can
   * say what it is able to undo.
   */
  enrollmentsByUser: Record<string, EnrollmentRead[]>
  isLoading: boolean
  isError: boolean
}

/**
 * Who is already enrolled in each of the given courses, keyed by user id.
 *
 * One request per course rather than one unfiltered `/enrollments` read: that endpoint
 * defaults to 50 rows and caps at 100, so "every enrollment in the org" is exactly the
 * query that silently truncates. A folder holds a handful of courses and the assignment
 * dialog needs the answer for all of the org's people, so the cheap axis is the course.
 *
 * The 100-row cap still applies per course. It can only ever *under*-report someone as
 * not enrolled, which costs the admin a redundant tick — the server skips the duplicate
 * either way. The key stays under `['enrollments']` so assigning invalidates it.
 */
export function useFolderCourseEnrollments(courseIds: string[]): FolderCourseEnrollments {
  const queries = useQueries({
    queries: courseIds.map((courseId) => ({
      queryKey: ['enrollments', 'by-course', courseId],
      queryFn: () =>
        get<Paginated<EnrollmentRead>>(`/enrollments?course_id=${courseId}&limit=100`),
      staleTime: 30_000,
    })),
  })

  const enrolledCountByUser: Record<string, number> = {}
  const enrollmentsByUser: Record<string, EnrollmentRead[]> = {}
  queries.forEach((query) => {
    query.data?.items.forEach((enrollment) => {
      enrolledCountByUser[enrollment.user_id] =
        (enrolledCountByUser[enrollment.user_id] ?? 0) + 1
      const rows = enrollmentsByUser[enrollment.user_id]
      if (rows) rows.push(enrollment)
      else enrollmentsByUser[enrollment.user_id] = [enrollment]
    })
  })

  return {
    enrolledCountByUser,
    enrollmentsByUser,
    isLoading: queries.some((query) => query.isLoading),
    isError: queries.some((query) => query.isError),
  }
}

export function useAssignCourseFolder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, userIds, deadline }: { id: string; userIds: string[]; deadline?: string }) =>
      post<CourseFolderAssignmentResult>(`/course-folders/${id}/assign`, {
        user_ids: userIds,
        deadline: deadline || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['enrollments'] })
      queryClient.invalidateQueries({ queryKey: ['talent'] })
    },
  })
}
