import { BrowserRouter, Routes, Route, Navigate, useParams, useLocation } from 'react-router-dom'
import { Toaster } from 'sonner'
import { AppLayout } from './components/layout/AppLayout'
import { AdminLayout } from './components/layout/AdminLayout'
import { ProtectedRoute } from './components/layout/ProtectedRoute'
import { useAuth, useWorkspaceMode } from './hooks/useAuth'
import { IntlProvider } from './i18n/IntlProvider'
import { useRegisterDefaultTools } from './stores/registerDefaultTools'
import { usePreferences } from './stores/preferences'
import { useTheme } from './hooks/useTheme'
import { Login } from './pages/auth/Login'
import { Setup } from './pages/setup/Setup'
import { useSetupStatus } from './api/setup'
import { Onboarding } from './pages/onboarding/Onboarding'
import { Dashboard } from './pages/employee/Dashboard'
import { MyCourses } from './pages/employee/MyCourses'
import { CourseView } from './pages/employee/CourseView'
import { NodeView } from './pages/employee/NodeView'
import { SkillMap } from './pages/employee/SkillMap'
import { Chat } from './pages/employee/Chat'
import { LearningPreferencesPage } from './pages/employee/LearningPreferences'
import { Dashboard as AdminDashboard } from './pages/admin/Dashboard'
import { Employees } from './pages/admin/Employees'
import { Talent } from './pages/admin/Talent'
import { Content } from './pages/admin/Content'
import { CreateCourse } from './pages/admin/CreateCourse'
import { AdminChat } from './pages/admin/Chat'
import { CoursePreview } from './pages/admin/CoursePreview'
import { DemoLesson } from './pages/admin/DemoLesson'
import { CourseSchema } from './pages/admin/CourseSchema'
import { Settings as AdminSettings } from './pages/admin/Settings'
import { MotionDemo } from './pages/dev/MotionDemo'
import { DidactLab } from './pages/dev/DidactLab'

function RedirectCourseEstudio() {
  const { id } = useParams<{ id: string }>()
  return <Navigate to={`/admin/probar-curso/${id}`} replace />
}

function RedirectCourseEsquema() {
  const { id } = useParams<{ id: string }>()
  return <Navigate to={`/admin/curso/${id}/ajustes`} replace />
}

const HOME_BY_ROLE = {
  admin: '/admin',
  employee: '/empleado',
} as const

function RootRedirect() {
  const { user, isLoading } = useAuth()
  if (isLoading) return null
  if (!user) return <Navigate to="/login" replace />
  return <Navigate to={HOME_BY_ROLE[user.role]} replace />
}

/**
 * First-boot gate. Until the deployment has an owner, every route redirects to
 * the `/setup` wizard; once it does, `/setup` redirects away. Fails open — if the
 * status probe errors we assume initialized, so a transient failure never traps
 * anyone in setup. See docs/design/audience-modes.md.
 */
function SetupBoundary({ children }: { children: React.ReactNode }) {
  const { data, isLoading } = useSetupStatus()
  const location = useLocation()
  if (isLoading) return null
  const initialized = data?.initialized ?? true
  if (!initialized && location.pathname !== '/setup') return <Navigate to="/setup" replace />
  if (initialized && location.pathname === '/setup') return <Navigate to="/login" replace />
  return <>{children}</>
}

/**
 * Collective, organization-only admin pages (Employees, Talent). In an
 * `individual` deployment these concepts do not exist: the nav omits them and a
 * direct URL redirects home. The backend also 404s their endpoints — this is UX,
 * not the authorization boundary. See docs/design/audience-modes.md.
 */
function OrganizationOnly({ children }: { children: React.ReactNode }) {
  const mode = useWorkspaceMode()
  if (mode === 'individual') return <Navigate to="/admin" replace />
  return <>{children}</>
}

function SonnerToaster() {
  const theme = usePreferences((s) => s.theme)
  return <Toaster richColors position="top-center" theme={theme} />
}

function App() {
  useRegisterDefaultTools()
  // Installs the effect that keeps <html data-theme> in sync with the stored
  // preference (and follows the OS while on `system`).
  useTheme()

  return (
    <IntlProvider>
      <SonnerToaster />
      <BrowserRouter>
        <SetupBoundary>
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/login" element={<Login />} />
          <Route path="/setup" element={<Setup />} />

          {/* Outside AppLayout on purpose (§13, B8): the wizard is the whole screen,
              and `skipOnboardingGate` is what keeps the gate in ProtectedRoute from
              redirecting /onboarding to itself. */}
          {/* No `role`: an employee onboards, and so does the admin owner of an
              `individual` deployment. The gate in ProtectedRoute only sends
              learners here, so no organization admin lands on it by accident. */}
          <Route
            path="/onboarding"
            element={
              <ProtectedRoute skipOnboardingGate>
                <Onboarding />
              </ProtectedRoute>
            }
          />

          <Route
            path="/empleado"
            element={
              <ProtectedRoute role="employee">
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Dashboard />} />
            <Route path="cursos" element={<MyCourses />} />
            <Route path="curso/:id" element={<CourseView />} />
            {/* The node view of a dynamic course (§13, B9). Mounted unconditionally: with
                the flag anywhere but `on` the runtime routes 404 and the screen explains
                that the course is served in its v1 format, which beats a route that
                silently does not exist. */}
            <Route path="curso/:id/nodo/:nodeId" element={<NodeView />} />
            <Route path="skillmap" element={<SkillMap />} />
            <Route path="chat" element={<Chat />} />
            <Route path="ajustes" element={<LearningPreferencesPage />} />
          </Route>

          <Route
            path="/admin"
            element={
              <ProtectedRoute role="admin">
                <AdminLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<AdminDashboard />} />
            <Route path="demo" element={<DemoLesson />} />
            <Route
              path="empleados"
              element={
                <OrganizationOnly>
                  <Employees />
                </OrganizationOnly>
              }
            />
            <Route
              path="talento"
              element={
                <OrganizationOnly>
                  <Talent />
                </OrganizationOnly>
              }
            />
            <Route path="contenido" element={<Content />} />
            <Route path="crear-curso" element={<CreateCourse />} />
            <Route path="curso/:id" element={<CoursePreview />} />
            <Route path="curso/:id/estudio" element={<RedirectCourseEstudio />} />
            <Route path="curso/:id/ajustes" element={<CourseSchema />} />
            <Route path="curso/:id/esquema" element={<RedirectCourseEsquema />} />
            {/* Admin course testing — same components the learner uses, rendered
                inside AdminLayout so the admin stays in context. */}
            <Route path="probar-curso/:id" element={<CourseView />} />
            <Route path="probar-curso/:id/nodo/:nodeId" element={<NodeView />} />
            <Route path="chat" element={<AdminChat />} />
            <Route path="ajustes" element={<AdminSettings />} />
          </Route>

          <Route path="/dev/motion" element={<MotionDemo />} />
          <Route
            path="/dev/didact"
            element={
              <ProtectedRoute role="admin">
                <DidactLab />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </SetupBoundary>
      </BrowserRouter>
    </IntlProvider>
  )
}

export default App
