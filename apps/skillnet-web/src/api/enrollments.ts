import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post } from './client'
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
