import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { get, post, loginRequest } from './client'
import type { User } from '../types'

export function useMe() {
  return useQuery({
    queryKey: ['users', 'me'],
    queryFn: () => get<User>('/auth/me'),
    retry: false, // never retry the auth probe
    staleTime: 5 * 60_000, // user data rarely changes mid-session
  })
}

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (credentials: { email: string; password: string }) => {
      await loginRequest(credentials.email, credentials.password)
      // Cookie is set — fetch the authenticated identity.
      return get<User>('/auth/me')
    },
    onSuccess: (user) => {
      queryClient.setQueryData(['users', 'me'], user)
    },
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => post('/auth/logout'),
    onSuccess: () => {
      queryClient.clear() // wipe all cached data on logout
      window.location.href = '/login'
    },
  })
}
