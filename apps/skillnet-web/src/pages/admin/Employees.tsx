import { useState } from 'react'
import { motion } from 'framer-motion'
import { Card, CardTitle, Badge, Button, Input, EmptyState, SkeletonRow, Modal } from '../../components/ui'
import { useUsers, useCreateUser, useResetPassword } from '../../api/users'
import { useCourses } from '../../api/courses'
import { useEnrollments, useAssignCourse } from '../../api/enrollments'
import { ApiError } from '../../api/client'
import { staggerContainer, staggerItem } from '../../lib/motion'
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
      <div>
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
      </div>
    )
  }

  return (
    <div>
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
    </div>
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

function ResetPasswordForm({ employee, onDone }: { employee: User; onDone: () => void }) {
  const [password, setPassword] = useState('')
  const reset = useResetPassword()
  const tooShort = password.length > 0 && password.length < 6

  function submit() {
    if (!password.trim() || tooShort || reset.isPending) return
    reset.mutate(
      { userId: employee.id, newPassword: password.trim() },
      { onSuccess: () => setPassword('') },
    )
  }

  if (reset.isSuccess) {
    return (
      <div>
        <CardTitle className="mb-2">Contraseña actualizada</CardTitle>
        <p className="text-sm text-text-secondary">
          La contraseña de {employee.full_name} fue cambiada correctamente.
        </p>
        <div className="flex justify-end mt-4">
          <Button size="sm" onClick={onDone}>Cerrar</Button>
        </div>
      </div>
    )
  }

  return (
    <div>
      <CardTitle className="mb-3">Restablecer contraseña</CardTitle>
      <p className="text-sm text-text-secondary mb-3">
        Nueva contraseña para {employee.full_name}
      </p>
      <Input
        label="Nueva contraseña"
        type="text"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Minimo 6 caracteres"
      />
      {tooShort && (
        <p className="text-sm text-danger mt-2">La contraseña debe tener al menos 6 caracteres.</p>
      )}
      {reset.isError && (
        <p className="text-sm text-danger mt-2">
          {reset.error instanceof ApiError ? reset.error.body.detail : 'No se pudo restablecer la contraseña'}
        </p>
      )}
      <div className="flex gap-2 mt-4 justify-end">
        <Button size="sm" variant="ghost" onClick={onDone}>Cancelar</Button>
        <Button size="sm" onClick={submit} disabled={reset.isPending || !password.trim() || tooShort}>
          {reset.isPending ? 'Guardando...' : 'Restablecer'}
        </Button>
      </div>
    </div>
  )
}

function EmployeeDetail({ employee }: { employee: User }) {
  const { data: enrollmentData, isLoading } = useEnrollments({ user_id: employee.id })
  const enrollments = enrollmentData?.items ?? []
  const [showResetPw, setShowResetPw] = useState(false)

  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 pr-8">
          <h3 className="text-lg font-semibold text-text truncate">{employee.full_name}</h3>
          <p className="text-sm text-text-secondary truncate">{employee.email}</p>
        </div>
        <Button size="sm" variant="ghost" onClick={() => setShowResetPw(true)}>
          Restablecer contraseña
        </Button>
      </div>

      <div className="mt-6">
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

      {showResetPw && (
        <Modal open={showResetPw} onClose={() => setShowResetPw(false)} size="sm">
          <ResetPasswordForm employee={employee} onDone={() => setShowResetPw(false)} />
        </Modal>
      )}
    </div>
  )
}

export function Employees() {
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<User | null>(null)
  const [creating, setCreating] = useState(false)
  const [createOrigin, setCreateOrigin] = useState<DOMRect | null>(null)
  const [detailOrigin, setDetailOrigin] = useState<DOMRect | null>(null)
  const { data, isLoading, error } = useUsers({ role: 'employee', search: search || undefined })

  function openDetail(emp: User, e: { currentTarget: Element }) {
    setDetailOrigin(e.currentTarget.getBoundingClientRect())
    setSelected(emp)
  }

  const employees = data?.items ?? []

  return (
    <div className="flex flex-col md:h-[calc(100dvh-50px-3rem)]">
      <div className="shrink-0 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-text">Empleados</h2>
          <p className="text-sm text-text-secondary mt-1">{data?.total ?? employees.length} miembros del equipo</p>
        </div>
        <Button
          variant="primary"
          size="md"
          onClick={(e) => {
            setCreateOrigin(e.currentTarget.getBoundingClientRect())
            setCreating(true)
          }}
        >
          Agregar empleado
        </Button>
      </div>

      <div className="shrink-0 relative mt-4">
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

      {/* Desktop table */}
      <Card className="mt-4 p-0 overflow-hidden hidden md:flex md:flex-col min-h-0">
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
          <div className="overflow-x-auto overflow-y-auto flex-1 min-h-0">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10">
                <tr className="border-b border-border bg-bg-subtle">
                  <th className="text-left py-3 px-5 font-medium text-text-secondary rounded-tl-xl">Nombre</th>
                  <th className="text-left py-3 px-4 font-medium text-text-secondary">Correo</th>
                  <th className="text-left py-3 px-4 font-medium text-text-secondary rounded-tr-xl">Rol</th>
                </tr>
              </thead>
              <motion.tbody initial="hidden" animate="visible" variants={staggerContainer}>
                {employees.map((emp) => (
                  <motion.tr
                    key={emp.id}
                    variants={staggerItem}
                    className="border-b border-border last:border-b-0 hover:bg-bg-subtle transition-colors cursor-pointer"
                    onClick={(e) => openDetail(emp, e)}
                  >
                    <td className="py-3 px-5"><span className="font-medium text-text">{emp.full_name}</span></td>
                    <td className="py-3 px-4 text-text-secondary">{emp.email}</td>
                    <td className="py-3 px-4">
                      <Badge variant="primary" badgeStyle="plain">{emp.role === 'admin' ? 'Admin' : 'Empleado'}</Badge>
                    </td>
                  </motion.tr>
                ))}
              </motion.tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Mobile cards. The loading branch is a real placeholder and not `!isLoading &&`:
          below `md` the desktop card above is `display: none`, so with nothing here the
          whole list reserved zero height and the page grew by the full list the moment
          the data landed. One card per skeleton, so the placeholder has the shape of
          what replaces it. */}
      {isLoading ? (
        <div className="mt-4 space-y-3 md:hidden">
          <Card><SkeletonRow /></Card>
          <Card><SkeletonRow /></Card>
          <Card><SkeletonRow /></Card>
        </div>
      ) : (
        <motion.div className="mt-4 space-y-3 md:hidden" initial="hidden" animate="visible" variants={staggerContainer}>
          {!error && employees.map((emp) => (
            <motion.div key={emp.id} variants={staggerItem}>
              <Card variant="interactive" onClick={(e) => openDetail(emp, e)}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-medium text-text truncate">{emp.full_name}</p>
                    <p className="text-sm text-text-secondary mt-0.5 truncate">{emp.email}</p>
                  </div>
                  <Badge variant="primary" badgeStyle="plain">{emp.role === 'admin' ? 'Admin' : 'Empleado'}</Badge>
                </div>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      )}

      {/* Create-employee modal */}
      <Modal open={creating} onClose={() => setCreating(false)} size="lg" origin={createOrigin}>
        <CreateEmployeeForm onDone={() => setCreating(false)} />
      </Modal>

      {/* Employee-detail modal */}
      <Modal open={!!selected} onClose={() => setSelected(null)} size="md" origin={detailOrigin}>
        {selected && <EmployeeDetail employee={selected} />}
      </Modal>
    </div>
  )
}
