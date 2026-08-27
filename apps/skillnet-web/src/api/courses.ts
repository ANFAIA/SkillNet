import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from './client'
import type {
  CourseDetail,
  CourseGenerationState,
  CourseProgress,
  CourseRead,
  Exercise,
  Lesson,
  Paginated,
} from '../types'

export interface CourseFilters {
  status?: string
  search?: string
  folderId?: string | null
  unorganized?: boolean
  /**
   * Filter by the creation-run state (migration 0025), not by `status`.
   *
   * Server-side on purpose: a course whose creation died is still `status: 'draft'`, so
   * finding the failures by filtering the fetched page client-side would only ever find
   * the ones that happened to be on it.
   */
  generationState?: CourseGenerationState
  offset?: number
  limit?: number
}

export function useCourses(filters?: CourseFilters) {
  return useQuery({
    queryKey: ['courses', filters ?? {}],
    queryFn: () => {
      const params = new URLSearchParams()
      if (filters?.status) params.set('status', filters.status)
      if (filters?.search) params.set('search', filters.search)
      if (filters?.folderId) params.set('folder_id', filters.folderId)
      if (filters?.unorganized) params.set('unorganized', 'true')
      if (filters?.generationState) params.set('generation_state', filters.generationState)
      params.set('offset', String(filters?.offset ?? 0))
      params.set('limit', String(filters?.limit ?? 100))
      return get<Paginated<CourseRead>>(`/courses?${params.toString()}`)
    },
  })
}

export function useCourse(id: string | undefined) {
  return useQuery({
    queryKey: ['courses', id],
    queryFn: () => get<CourseDetail>(`/courses/${id}`),
    enabled: !!id,
  })
}

export function useCreateCourse() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: {
      title: string
      description?: string
      outcome?: string
      source_document_id?: string
    }) => post<CourseRead>('/courses', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['courses'] })
    },
  })
}

export function useUpdateCourse() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string
      payload: {
        title?: string
        description?: string
        outcome?: string
        folder_id?: string | null
        artifact_generate_policy?: 'admin' | 'everyone' | 'selected'
        artifact_generator_ids?: string[]
      }
    }) => put<CourseRead>(`/courses/${id}`, payload),
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['courses', id] })
      queryClient.invalidateQueries({ queryKey: ['courses'] })
    },
  })
}

export function useDeleteCourse() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => del(`/courses/${id}`),
    onSuccess: (_data, id) => {
      // Drop the detail rather than invalidate it: refetching a course that no longer
      // exists only buys a 404 for whatever screen is still holding it.
      queryClient.removeQueries({ queryKey: ['courses', id] })
      queryClient.invalidateQueries({ queryKey: ['courses'] })
      // The folder sidebar counts the courses it holds; one of them just left.
      queryClient.invalidateQueries({ queryKey: ['course-folders'] })
    },
  })
}

export function usePublishCourse() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (courseId: string) => post<CourseRead>(`/courses/${courseId}/publish`),
    onMutate: async (courseId) => {
      await queryClient.cancelQueries({ queryKey: ['courses', courseId] })
      const previous = queryClient.getQueryData<CourseDetail>(['courses', courseId])
      if (previous) {
        queryClient.setQueryData(['courses', courseId], { ...previous, status: 'published' })
      }
      return { previous }
    },
    onError: (_err, courseId, context) => {
      if (context?.previous) {
        queryClient.setQueryData(['courses', courseId], context.previous)
      }
    },
    onSettled: (_data, _err, courseId) => {
      queryClient.invalidateQueries({ queryKey: ['courses', courseId] })
      queryClient.invalidateQueries({ queryKey: ['courses'] })
    },
  })
}

export function useArchiveCourse() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (courseId: string) => post<CourseRead>(`/courses/${courseId}/archive`),
    onSuccess: (_data, courseId) => {
      queryClient.invalidateQueries({ queryKey: ['courses', courseId] })
      queryClient.invalidateQueries({ queryKey: ['courses'] })
    },
  })
}

export function useUpdateLesson() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      lessonId,
      payload,
    }: {
      lessonId: string
      payload: { title?: string; content?: string }
    }) => put<Lesson>(`/lessons/${lessonId}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['courses'] })
    },
  })
}

export function useUpdateExercise() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      exerciseId,
      payload,
    }: {
      exerciseId: string
      payload: { content?: Record<string, unknown> }
    }) => put<Exercise>(`/exercises/${exerciseId}`, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['courses'] })
    },
  })
}

export function useCourseProgress(courseId: string | undefined) {
  return useQuery({
    queryKey: ['courses', courseId, 'progress'],
    queryFn: () => get<CourseProgress>(`/courses/${courseId}/progress`),
    enabled: !!courseId,
  })
}

export function useCompleteLesson() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (lessonId: string) =>
      post<{ completed: boolean; progress?: number; reason?: string }>(
        `/lessons/${lessonId}/complete`,
      ),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['enrollments'] })
      queryClient.invalidateQueries({ queryKey: ['courses'] })
    },
  })
}

// Triggers the async generation pipeline. Returns a job id to track via SSE.
export function useGenerateContent() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (params: {
      courseId: string
      source_document_id?: string
      output_type?: string
    }) =>
      post<{ job_id: string }>(`/courses/${params.courseId}/generate`, {
        source_document_id: params.source_document_id,
        output_type: params.output_type,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['courses'] })
    },
  })
}
