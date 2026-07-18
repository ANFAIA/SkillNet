import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../../hooks/useAuth'
import type { UserRole } from '../../types'

const HOME_BY_ROLE: Record<UserRole, string> = {
  admin: '/admin',
  employee: '/empleado',
}

function AppSkeleton() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <img src="/logo.png" alt="SkillNet" className="w-10 h-10 drop-shadow-lg animate-pulse" />
        <div className="h-1.5 w-40 rounded-full bg-white/20 overflow-hidden">
          <div className="h-full w-1/2 rounded-full bg-white/60 animate-pulse" />
        </div>
      </div>
    </div>
  )
}

export function ProtectedRoute({
  role,
  children,
}: {
  role?: UserRole
  children: ReactNode
}) {
  const { user, isLoading } = useAuth()

  if (isLoading) return <AppSkeleton />
  if (!user) return <Navigate to="/login" replace />
  if (role && user.role !== role) return <Navigate to={HOME_BY_ROLE[user.role]} replace />

  return <>{children}</>
}
