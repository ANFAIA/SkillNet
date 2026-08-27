import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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
  /** Distinct people reached, after the server resolved every group. */
  person_count: number
  /** Group members left out because their account is deactivated. */
  skipped_inactive_count: number
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
  /**
   * True when the answer did not fit in one page, so the ticks are incomplete.
   *
   * The caller sizes its pages to keep this false; it is here because "impossible by
   * construction" and "silently wrong" look identical once the construction changes.
   */
  truncated: boolean
}

/**
 * Who, of these specific people, already holds each published course of this folder.
 *
 * **Bounded by construction.** One request, filtered on both axes at once:
 * `?folder_id=` resolves server-side to the folder's published courses (the same set
 * every assignment path uses) and `?user_ids=` narrows it to the page of people on
 * screen. The answer can therefore hold at most `people x courses` rows, and the caller
 * chooses a page size that keeps that under the endpoint's 100-row cap.
 *
 * That replaces one unfiltered read per course, which capped at 100 rows *each*: past a
 * hundred enrollments in a course it reported people as unenrolled who were not, and the
 * tick said "does not have this folder" about somebody who did. Under-reporting was
 * documented as harmless because the server skips duplicates anyway — but it is not
 * harmless for the *other* direction, where the tick is how the admin revokes.
 *
 * `truncated` is the honest escape hatch: if the response still did not fit, the caller
 * must not present the ticks as complete.
 */
export function useFolderCourseEnrollments(
  folderId: string,
  userIds: string[],
): FolderCourseEnrollments {
  // A stable key and a stable URL for the same page, whatever order the list arrived in.
  const sorted = [...userIds].sort()
  const query = useQuery({
    queryKey: ['enrollments', 'by-folder', folderId, sorted],
    queryFn: () => {
      const params = new URLSearchParams({ folder_id: folderId, limit: '100' })
      sorted.forEach((id) => params.append('user_ids', id))
      return get<Paginated<EnrollmentRead>>(`/enrollments?${params.toString()}`)
    },
    // No people on screen yet: there is nothing to ask about, and an unfiltered read is
    // exactly the query this hook exists to avoid.
    enabled: sorted.length > 0,
    staleTime: 30_000,
  })

  const enrolledCountByUser: Record<string, number> = {}
  const enrollmentsByUser: Record<string, EnrollmentRead[]> = {}
  query.data?.items.forEach((enrollment) => {
    enrolledCountByUser[enrollment.user_id] =
      (enrolledCountByUser[enrollment.user_id] ?? 0) + 1
    const rows = enrollmentsByUser[enrollment.user_id]
    if (rows) rows.push(enrollment)
    else enrollmentsByUser[enrollment.user_id] = [enrollment]
  })

  return {
    enrolledCountByUser,
    enrollmentsByUser,
    isLoading: sorted.length > 0 && query.isLoading,
    isError: query.isError,
    truncated: (query.data?.total ?? 0) > (query.data?.items.length ?? 0),
  }
}

export function useAssignCourseFolder() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      userIds,
      groupIds,
      deadline,
    }: {
      id: string
      userIds?: string[]
      /** Resolved to their members on the server, never in the browser. */
      groupIds?: string[]
      deadline?: string
    }) =>
      post<CourseFolderAssignmentResult>(`/course-folders/${id}/assign`, {
        user_ids: userIds ?? [],
        group_ids: groupIds ?? [],
        deadline: deadline || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['enrollments'] })
      queryClient.invalidateQueries({ queryKey: ['talent'] })
    },
  })
}
