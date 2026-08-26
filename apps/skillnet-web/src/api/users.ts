import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from './client'
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
    mutationFn: (payload: {
      email: string
      full_name: string
      password?: string
      /** Omitted means `employee`. `admin` is how an admin invites another admin. */
      role?: 'admin' | 'employee'
    }) => post<EmployeeCreated>('/users', payload),
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
   * The four reading settings of question 5 (`users.accessibility`).
   *
   * The onboarding wizard does **not** write them through here: `POST /onboarding`
   * persists `learner_profiles` + `users.learning_profile` + `users.accessibility`
   * in one transaction (§11.2), which is the only atomic path. This field is the
   * Settings-screen path for changing them afterwards, and `UserSelfUpdate` accepts
   * it server-side with the wizard's own validation (`AccessibilitySubmit`,
   * `extra='forbid'`), so an unknown key is a `422` rather than a silent drop.
   *
   * Send the **whole** object, not a partial: the server replaces the stored value
   * instead of merging, which is what lets an unchecked box turn a setting back off.
   * `short_blocks` feeds `effective_density` and therefore the render `cache_key`
   * (§3.1), so the next node the learner opens is rendered for the new bucket.
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

/** Toggle an employee's `is_active` — admin-side deactivate/reactivate, reversible. */
export function useSetEmployeeActive() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, isActive }: { userId: string; isActive: boolean }) =>
      put<User>(`/users/${userId}`, { is_active: isActive }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
}

/**
 * Promote a member to admin or demote them back to employee — the only two roles
 * that exist.
 *
 * Every rule lives on the server: an admin may only touch users of their own
 * organization, and the last active admin can be neither demoted nor deactivated.
 * The UI reads the resulting 403 and shows it; it does not try to predict it, so
 * there is one implementation of the safeguard and not two that can disagree.
 */
export function useSetUserRole() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: 'admin' | 'employee' }) =>
      put<User>(`/users/${userId}`, { role }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (payload: { current_password: string; new_password: string }) =>
      post<{ ok: boolean }>('/users/me/change-password', payload),
  })
}

export function useChangeEmail() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (payload: { new_email: string; current_password: string }) =>
      put<User>('/users/me/email', payload),
    onSuccess: (user) => {
      queryClient.setQueryData(['users', 'me'], user)
    },
  })
}

/** Individual workspace only (server-enforced, 404 otherwise) — see
 * `require_individual_workspace`. Soft-deletes: deactivates and frees the email. */
export function useDeleteAccount() {
  return useMutation({
    mutationFn: (payload: { current_password: string }) =>
      del<{ ok: boolean }>('/users/me', payload),
  })
}
