import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post, put } from './client'
import type { Paginated, User, UserSkillRead } from '../types'

export interface UserFilters {
  search?: string
  role?: string
  is_active?: boolean
}

function toQuery(filters?: UserFilters): string {
  if (!filters) return ''
  const params = new URLSearchParams()
  if (filters.search) params.set('search', filters.search)
  if (filters.role) params.set('role', filters.role)
  if (filters.is_active !== undefined) params.set('is_active', String(filters.is_active))
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

export function useUsers(filters?: UserFilters) {
  return useQuery({
    queryKey: ['users', filters ?? {}],
    queryFn: () => get<Paginated<User>>(`/users${toQuery(filters)}`),
  })
}

export function useUser(id: string) {
  return useQuery({
    queryKey: ['users', id],
    queryFn: () => get<User>(`/users/${id}`),
    enabled: !!id,
  })
}

export interface EmployeeCreated extends User {
  temporary_password?: string | null
}

export function useCreateUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: { email: string; full_name: string; password?: string }) =>
      post<EmployeeCreated>('/users', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
}

export function useUpdateProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: { full_name?: string; learning_profile?: Record<string, unknown> }) =>
      put<User>('/users/me', payload),
    onSuccess: (user) => {
      queryClient.setQueryData(['users', 'me'], user)
    },
  })
}

export function useMySkills() {
  return useQuery({
    queryKey: ['users', 'me', 'skills'],
    queryFn: () => get<UserSkillRead[]>('/users/me/skills'),
    staleTime: 60_000,
  })
}

export function useResetPassword() {
  return useMutation({
    mutationFn: ({ userId, newPassword }: { userId: string; newPassword: string }) =>
      post<{ ok: boolean }>(`/users/${userId}/reset-password`, { new_password: newPassword }),
  })
}
