import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'sonner'
import { AppLayout } from './components/layout/AppLayout'
import { AdminLayout } from './components/layout/AdminLayout'
import { ProtectedRoute } from './components/layout/ProtectedRoute'
import { useAuth } from './hooks/useAuth'
import { IntlProvider } from './i18n/IntlProvider'
import { useRegisterDefaultTools } from './stores/registerDefaultTools'
import { usePreferences } from './stores/preferences'
import { useTheme } from './hooks/useTheme'
import { Login } from './pages/auth/Login'
import { Onboarding } from './pages/onboarding/Onboarding'
import { Dashboard } from './pages/employee/Dashboard'
import { MyCourses } from './pages/employee/MyCourses'
import { CourseView } from './pages/employee/CourseView'
import { NodeView } from './pages/employee/NodeView'
import { SkillMap } from './pages/employee/SkillMap'
import { Chat } from './pages/employee/Chat'
import { Dashboard as AdminDashboard } from './pages/admin/Dashboard'
import { Employees } from './pages/admin/Employees'
import { Content } from './pages/admin/Content'
import { CreateCourse } from './pages/admin/CreateCourse'
import { AdminChat } from './pages/admin/Chat'
import { CoursePreview } from './pages/admin/CoursePreview'
import { CourseSchema } from './pages/admin/CourseSchema'
import { Settings as AdminSettings } from './pages/admin/Settings'
import { MotionDemo } from './pages/dev/MotionDemo'

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
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/login" element={<Login />} />

          {/* Outside AppLayout on purpose (§13, B8): the wizard is the whole screen,
              and `skipOnboardingGate` is what keeps the gate in ProtectedRoute from
              redirecting /onboarding to itself. */}
          <Route
            path="/onboarding"
            element={
              <ProtectedRoute role="employee" skipOnboardingGate>
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
            <Route path="empleados" element={<Employees />} />
            <Route path="contenido" element={<Content />} />
            <Route path="crear-curso" element={<CreateCourse />} />
            <Route path="curso/:id" element={<CoursePreview />} />
            {/* The creator's gate (§11.1, B10). Mounted unconditionally: the admin
                schema routes 404 with the flag off and the screen says so, which beats
                a route that silently does not exist. */}
            <Route path="curso/:id/esquema" element={<CourseSchema />} />
            {/* Admin course testing — same components the learner uses, rendered
                inside AdminLayout so the admin stays in context. */}
            <Route path="probar-curso/:id" element={<CourseView />} />
            <Route path="probar-curso/:id/nodo/:nodeId" element={<NodeView />} />
            <Route path="chat" element={<AdminChat />} />
            <Route path="ajustes" element={<AdminSettings />} />
          </Route>

          <Route path="/dev/motion" element={<MotionDemo />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </IntlProvider>
  )
}

export default App
