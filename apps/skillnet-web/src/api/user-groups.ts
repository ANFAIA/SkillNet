import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from './client'
import type { Paginated, User } from '../types'

export interface UserGroup {
  id: string
  name: string
  /** Everyone in the group, deactivated accounts included. */
  member_count: number
  created_at?: string
  updated_at?: string
}

export interface UserGroupMembersResult {
  added_count: number
  removed_count: number
  member_count: number
}

export interface UserGroupFilters {
  /** Matched against the name, case-insensitively, **server-side**. */
  search?: string
  /** Only the groups this person is **not** in — the "add to a group" list. */
  exclude_user_id?: string
  offset?: number
  limit?: number
}

/** Rows per page. The server caps `limit` at 100; ask for less and paginate. */
export const USER_GROUPS_PAGE_SIZE = 25

function toQuery(filters?: UserGroupFilters): string {
  const params = new URLSearchParams()
  if (filters?.search) params.set('search', filters.search)
  if (filters?.exclude_user_id) params.set('exclude_user_id', filters.exclude_user_id)
  // Always sent, never left to the server's default, for the same reason `useUsers`
  // sends them: the default is 50 and the response carries a `total`, so a caller that
  // omitted both would get the first fifty groups with nothing on screen saying there
  // was a fifty-first.
  params.set('offset', String(filters?.offset ?? 0))
  params.set('limit', String(filters?.limit ?? USER_GROUPS_PAGE_SIZE))
  return `?${params.toString()}`
}

/**
 * One page of the organization's groups.
 *
 * Paginated and searched server-side, like the people list it sits next to. Nothing
 * bounds how many groups an organization has, and the rail that renders them was
 * printing every one of them: at a few dozen it is a scroll, at a few hundred it is a
 * screen nobody can use and a request nobody asked for.
 *
 * `search` is a query parameter and not a `.filter()` on what came back — the response
 * is one page, so narrowing it here would only ever find the groups that happened to
 * land on it.
 */
export function useUserGroups(filters?: UserGroupFilters) {
  return useQuery({
    queryKey: ['user-groups', filters ?? {}],
    queryFn: () => get<Paginated<UserGroup>>(`/user-groups${toQuery(filters)}`),
  })
}

export function useCreateUserGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => post<UserGroup>('/user-groups', { name }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['user-groups'] }),
  })
}

export function useRenameUserGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      put<UserGroup>(`/user-groups/${id}`, { name }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['user-groups'] }),
  })
}

/**
 * Delete a group. Nobody is un-enrolled.
 *
 * `enrollments.source_group_id` is `ON DELETE SET NULL` on the server, so the training
 * the group handed out stays exactly where it is. The `['users']` invalidation is for
 * the group filter on the people list, which now points at a group that is gone.
 */
export function useDeleteUserGroup() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => del<void>(`/user-groups/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-groups'] })
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
}

/**
 * The groups one person belongs to.
 *
 * Read from the person's side (`GET /users/{id}/groups`) rather than assembled in the
 * browser from every group's membership: the employee record needs one answer about one
 * person, and building it here would mean a request per group.
 */
export function useGroupsOfPerson(userId: string | undefined) {
  return useQuery({
    queryKey: ['users', userId, 'groups'],
    queryFn: () => get<UserGroup[]>(`/users/${userId}/groups`),
    enabled: !!userId,
  })
}

/**
 * One page of a group's members.
 *
 * Paginated like every other people read: a group is a list of colleagues and there is
 * no ceiling on how many that is.
 */
export function useUserGroupMembers(
  groupId: string | undefined,
  { offset = 0, limit = 50 }: { offset?: number; limit?: number } = {},
) {
  return useQuery({
    queryKey: ['user-groups', groupId, 'members', { offset, limit }],
    queryFn: () =>
      get<Paginated<User>>(
        `/user-groups/${groupId}/members?offset=${offset}&limit=${limit}`,
      ),
    enabled: !!groupId,
  })
}

/**
 * Apply one membership edit: who joins and who leaves, in a single request.
 *
 * Both halves travel together because that is how the dialog produces them — a page of
 * ticks yields additions and removals at once — and two requests could half-apply.
 */
export function useUpdateUserGroupMembers() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, add, remove }: { id: string; add: string[]; remove: string[] }) =>
      put<UserGroupMembersResult>(`/user-groups/${id}/members`, { add, remove }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-groups'] })
      // `['users']` covers both the people list (filterable by group) and the per-person
      // `['users', id, 'groups']` read, so an edit made from either side repaints both.
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
  })
}
