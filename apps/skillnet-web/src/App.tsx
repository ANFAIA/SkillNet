import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AppLayout } from './components/layout/AppLayout'
import { AdminLayout } from './components/layout/AdminLayout'
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

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/empleado" element={<AppLayout />}>
          <Route index element={<Dashboard />} />
          <Route path="cursos" element={<MyCourses />} />
          <Route path="curso/:id" element={<CourseView />} />
          <Route path="skillmap" element={<SkillMap />} />
          <Route path="chat" element={<Chat />} />
        </Route>
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<AdminDashboard />} />
          <Route path="empleados" element={<Employees />} />
          <Route path="contenido" element={<Content />} />
          <Route path="crear-curso" element={<CreateCourse />} />
          <Route path="chat" element={<AdminChat />} />
        </Route>
        <Route path="*" element={<Navigate to="/empleado" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
