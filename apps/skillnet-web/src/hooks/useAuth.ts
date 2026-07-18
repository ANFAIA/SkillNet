import { useMe } from '../api/auth'

export function useAuth() {
  const { data: user, isLoading, error } = useMe()
  return { user, isLoading, isAuthenticated: !!user, error }
}
