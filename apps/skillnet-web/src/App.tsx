import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { AdminLayout } from './components/layout/AdminLayout'
import { ProtectedRoute } from './components/layout/ProtectedRoute'
import { useAuth } from './hooks/useAuth'
import { Login } from './pages/auth/Login'
import { Dashboard } from './pages/employee/Dashboard'
import { MyCourses } from './pages/employee/MyCourses'
import { CourseView } from './pages/employee/CourseView'
import { SkillMap } from './pages/employee/SkillMap'
import { Chat } from './pages/employee/Chat'
import { Dashboard as AdminDashboard } from './pages/admin/Dashboard'
import { Employees } from './pages/admin/Employees'
import { Content } from './pages/admin/Content'
import { CreateCourse } from './pages/admin/CreateCourse'
import { AdminChat } from './pages/admin/Chat'
import { CoursePreview } from './pages/admin/CoursePreview'
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

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RootRedirect />} />
        <Route path="/login" element={<Login />} />

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
          <Route path="chat" element={<AdminChat />} />
          <Route path="ajustes" element={<AdminSettings />} />
        </Route>

        <Route path="/dev/motion" element={<MotionDemo />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
