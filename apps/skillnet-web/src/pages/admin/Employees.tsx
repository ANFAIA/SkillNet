import { useState } from 'react'
import { Card, CardTitle, Badge, Button, Input, EmptyState, SkeletonRow } from '../../components/ui'
import { useUsers, useCreateUser } from '../../api/users'
import { useCourses } from '../../api/courses'
import { useEnrollments, useAssignCourse } from '../../api/enrollments'
import { ApiError } from '../../api/client'
import type { User } from '../../types'

function SearchIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
    </svg>
  )
}

function CreateEmployeeForm({ onDone }: { onDone: () => void }) {
  const create = useCreateUser()
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')

  const created = create.data
  const passwordTooShort = password.length > 0 && password.length < 8

  function submit() {
    if (!email.trim() || !fullName.trim() || passwordTooShort || create.isPending) return
    create.mutate({
      email: email.trim(),
      full_name: fullName.trim(),
      password: password.trim() || undefined,
    })
  }

  if (created) {
    const shownPassword = created.temporary_password ?? password
    return (
      <Card className="mt-4">
        <CardTitle className="mb-2">Empleado creado</CardTitle>
        <p className="text-sm text-text-secondary mb-3">
          Comparte estas credenciales con {created.full_name}. La contraseña no se volvera a mostrar.
        </p>
        <div className="rounded-lg border border-border bg-bg-subtle p-3 text-sm space-y-1">
          <div><span className="text-text-muted">Correo:</span> <span className="font-medium text-text">{created.email}</span></div>
          <div><span className="text-text-muted">Contraseña:</span> <span className="font-mono font-medium text-text">{shownPassword}</span></div>
        </div>
        <div className="flex gap-2 mt-4">
          <Button size="sm" onClick={onDone}>Listo</Button>
        </div>
      </Card>
    )
  }

  return (
    <Card className="mt-4">
      <CardTitle className="mb-3">Nuevo empleado</CardTitle>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Input label="Nombre completo" value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Ej: Laura Martinez" />
        <Input label="Correo" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="laura@empresa.com" />
        <Input
          label="Contraseña (opcional)"
          type="text"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Se genera una si la dejas vacia"
        />
      </div>
      {passwordTooShort && (
        <p className="text-sm text-danger mt-2">La contraseña debe tener al menos 8 caracteres.</p>
      )}
      {create.isError && (
        <p className="text-sm text-danger mt-2">
          {create.error instanceof ApiError ? create.error.body.detail : 'No se pudo crear el empleado'}
        </p>
      )}
      <div className="flex gap-2 mt-4">
        <Button size="sm" onClick={submit} disabled={create.isPending || !email.trim() || !fullName.trim() || passwordTooShort}>
          {create.isPending ? 'Creando...' : 'Crear empleado'}
        </Button>
        <Button size="sm" variant="ghost" onClick={onDone}>Cancelar</Button>
      </div>
    </Card>
  )
}

function AssignCourseForm({ user }: { user: User }) {
  const { data: courseData } = useCourses({ status: 'published' })
  const assign = useAssignCourse()
  const [courseId, setCourseId] = useState('')
  const [deadline, setDeadline] = useState('')
  const courses = courseData?.items ?? []

  function submit() {
    if (!courseId || assign.isPending) return
    assign.mutate(
      { user_ids: [user.id], course_id: courseId, deadline: deadline || undefined },
      {
        onSuccess: () => {
          setCourseId('')
          setDeadline('')
        },
      },
    )
  }

  return (
    <div className="mt-3 space-y-3">
      <div>
        <label className="block text-sm font-medium text-text mb-1">Curso</label>
        <select
          value={courseId}
          onChange={(e) => setCourseId(e.target.value)}
          className="w-full px-3 py-2 text-sm text-text border border-border rounded-lg bg-bg focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors"
        >
          <option value="">Selecciona un curso</option>
          {courses.map((c) => (
            <option key={c.id} value={c.id}>{c.title}</option>
          ))}
        </select>
      </div>
      <Input label="Fecha limite (opcional)" type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
      {assign.isError && (
        <p className="text-sm text-danger">
          {assign.error instanceof ApiError ? assign.error.body.detail : 'No se pudo asignar el curso'}
        </p>
      )}
      {assign.isSuccess && <p className="text-sm text-accent">Curso asignado correctamente.</p>}
      <Button size="sm" onClick={submit} disabled={!courseId || assign.isPending}>
        {assign.isPending ? 'Asignando...' : 'Asignar curso'}
      </Button>
    </div>
  )
}

function EmployeeDetail({ employee, onBack }: { employee: User; onBack: () => void }) {
  const { data: enrollmentData, isLoading } = useEnrollments({ user_id: employee.id })
  const enrollments = enrollmentData?.items ?? []

  return (
    <div>
      <button type="button" onClick={onBack} className="text-sm text-primary hover:underline cursor-pointer mb-4">
        Volver a la lista
      </button>
      <Card>
        <div className="min-w-0">
          <h3 className="text-lg font-semibold text-text truncate">{employee.full_name}</h3>
          <p className="text-sm text-text-secondary truncate">{employee.email}</p>
        </div>

        <div className="mt-5">
          <CardTitle>Cursos asignados</CardTitle>
          <div className="mt-3">
            {isLoading ? (
              <SkeletonRow />
            ) : enrollments.length === 0 ? (
              <p className="text-sm text-text-muted">Sin cursos asignados.</p>
            ) : (
              <div className="space-y-0">
                {enrollments.map((e) => (
                  <div key={e.id} className="flex items-center justify-between py-2.5 border-b border-border last:border-b-0">
                    <span className="text-sm text-text truncate min-w-0">{e.course_title}</span>
                    <span className="text-xs text-text-muted shrink-0 ml-4">{e.progress ?? 0}%</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="mt-5 border-t border-border pt-5">
          <CardTitle>Asignar nuevo curso</CardTitle>
          <AssignCourseForm user={employee} />
        </div>
      </Card>
    </div>
  )
}

export function Employees() {
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<User | null>(null)
  const [creating, setCreating] = useState(false)
  const { data, isLoading, error } = useUsers({ role: 'employee', search: search || undefined })

  const employees = data?.items ?? []

  if (selected) {
    return <EmployeeDetail employee={selected} onBack={() => setSelected(null)} />
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-text">Empleados</h2>
          <p className="text-sm text-text-secondary mt-1">{data?.total ?? employees.length} miembros del equipo</p>
        </div>
        <Button variant="primary" size="md" onClick={() => setCreating((v) => !v)}>
          {creating ? 'Cerrar' : 'Agregar empleado'}
        </Button>
      </div>

      {creating && <CreateEmployeeForm onDone={() => setCreating(false)} />}

      <div className="relative mt-4">
        <div className="absolute inset-y-0 left-3 flex items-center pointer-events-none text-text-muted">
          <SearchIcon />
        </div>
        <input
          type="text"
          placeholder="Buscar por nombre o correo..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-9 pr-3 py-2 text-sm text-text border border-border rounded-lg bg-bg placeholder:text-text-muted focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors"
        />
      </div>

      <Card className="mt-4 p-0 overflow-hidden hidden md:block">
        {isLoading ? (
          <div className="p-4 space-y-1">
            <SkeletonRow />
            <SkeletonRow />
            <SkeletonRow />
          </div>
        ) : error ? (
          <EmptyState title="No se pudieron cargar los empleados" />
        ) : employees.length === 0 ? (
          <EmptyState title="No se encontraron empleados" description="Agrega tu primer empleado" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-bg-subtle">
                  <th className="text-left py-3 px-5 font-medium text-text-secondary">Nombre</th>
                  <th className="text-left py-3 px-4 font-medium text-text-secondary">Correo</th>
                  <th className="text-left py-3 px-4 font-medium text-text-secondary">Rol</th>
                </tr>
              </thead>
              <tbody>
                {employees.map((emp) => (
                  <tr
                    key={emp.id}
                    className="border-b border-border last:border-b-0 hover:bg-bg-subtle transition-colors cursor-pointer"
                    onClick={() => setSelected(emp)}
                  >
                    <td className="py-3 px-5"><span className="font-medium text-text">{emp.full_name}</span></td>
                    <td className="py-3 px-4 text-text-secondary">{emp.email}</td>
                    <td className="py-3 px-4">
                      <Badge variant="primary" badgeStyle="plain">{emp.role === 'admin' ? 'Admin' : 'Empleado'}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="mt-4 space-y-3 md:hidden">
        {!isLoading && !error && employees.map((emp) => (
          <Card key={emp.id} variant="interactive" onClick={() => setSelected(emp)}>
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-medium text-text truncate">{emp.full_name}</p>
                <p className="text-sm text-text-secondary mt-0.5 truncate">{emp.email}</p>
              </div>
              <Badge variant="primary" badgeStyle="plain">{emp.role === 'admin' ? 'Admin' : 'Empleado'}</Badge>
            </div>
          </Card>
        ))}
      </div>
    </div>
  )
}
