import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from './client'
import type { CourseDetail, CourseRead, Paginated } from '../types'

export interface CourseFilters {
  status?: string
}

export function useCourses(filters?: CourseFilters) {
  return useQuery({
    queryKey: ['courses', filters ?? {}],
    queryFn: () =>
      get<Paginated<CourseRead>>(
        `/courses${filters?.status ? `?status=${filters.status}` : ''}`,
      ),
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
      payload: { title?: string; description?: string; outcome?: string }
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['courses'] })
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
