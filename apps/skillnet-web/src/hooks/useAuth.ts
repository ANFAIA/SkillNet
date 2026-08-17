import { useMe } from '../api/auth'
import type { WorkspaceMode } from '../types'

export function useAuth() {
  const { data: user, isLoading, error } = useMe()
  return { user, isLoading, isAuthenticated: !!user, error }
}

/**
 * The deployment's workspace mode, from `/auth/me`. Defaults to 'organization'
 * — the mode every existing deployment runs in — until the identity loads or
 * when the field is absent. See docs/design/audience-modes.md.
 */
export function useWorkspaceMode(): WorkspaceMode {
  const { data: user } = useMe()
  return user?.workspace_mode ?? 'organization'
}
