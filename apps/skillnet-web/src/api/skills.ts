import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post, put } from './client'
import type { Paginated } from '../types'

export interface SkillRead {
  id: string
  name: string
  description: string | null
}

export function useSkills(search = '', options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ['skills', { search }],
    queryFn: () => {
      const params = new URLSearchParams({ offset: '0', limit: '100' })
      if (search.trim()) params.set('search', search.trim())
      return get<Paginated<SkillRead>>(`/skills?${params.toString()}`)
    },
    staleTime: 60_000,
    // The skills catalogue is a talent (organization-only) concept: it 404s in an
    // individual workspace, so callers there disable the query.
    enabled: options?.enabled ?? true,
  })
}

export function useCreateSkill() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: { name: string; description?: string }) =>
      post<SkillRead>('/skills', payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['skills'] }),
  })
}

export function useUpdateSkill() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...payload }: { id: string; name?: string; description?: string | null }) =>
      put<SkillRead>(`/skills/${id}`, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['skills'] }),
  })
}

export function useReplaceCourseSkills() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ courseId, skills }: {
      courseId: string
      skills: Array<{ id?: string; name?: string; description?: string | null }>
    }) => put<SkillRead[]>(`/courses/${courseId}/skills`, { skills }),
    onSuccess: (data, variables) => {
      queryClient.setQueryData(['courses', variables.courseId, 'skills'], data)
      queryClient.invalidateQueries({ queryKey: ['skills'] })
      queryClient.invalidateQueries({ queryKey: ['talent'] })
    },
  })
}

export function useCourseSkills(courseId?: string) {
  return useQuery({
    queryKey: ['courses', courseId, 'skills'],
    queryFn: () => get<SkillRead[]>(`/courses/${courseId}/skills`),
    enabled: !!courseId,
  })
}
