import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post, put } from './client'
import type { AccessibilitySettings, LearningPreset } from './onboarding'
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

export interface ProfileUpdate {
  full_name?: string
  /**
   * `users.learning_profile` is the `learning_profile` enum, not a JSON blob, so
   * the value is a plain string (§13, B8). The previous
   * `Record<string, unknown>` made it impossible to send.
   */
  learning_profile?: LearningPreset
  /**
   * The four reading settings of question 5.
   *
   * The onboarding wizard does **not** write them through here: `POST /onboarding`
   * persists `learner_profiles` + `users.learning_profile` + `users.accessibility`
   * in one transaction (§11.2), which is the only atomic path. This field is for
   * the Settings screen, and it needs `UserSelfUpdate` to grow an `accessibility`
   * field server-side before it does anything — see the report for B8.
   */
  accessibility?: AccessibilitySettings
}

export function useUpdateProfile() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: ProfileUpdate) => put<User>('/users/me', payload),
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
