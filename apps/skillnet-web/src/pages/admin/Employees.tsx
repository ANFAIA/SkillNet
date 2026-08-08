import { useState } from 'react'
import { useIntl } from 'react-intl'
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
  const intl = useIntl()
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
        <CardTitle className="mb-2">{intl.formatMessage({ id: 'employees.created' })}</CardTitle>
        <p className="text-sm text-text-secondary mb-3">
          {intl.formatMessage({ id: 'employees.createdShareCreds' }, { name: created.full_name })}
        </p>
        <div className="rounded-lg border border-border bg-bg-subtle p-3 text-sm space-y-1">
          <div><span className="text-text-muted">{intl.formatMessage({ id: 'employees.email' })}</span> <span className="font-medium text-text">{created.email}</span></div>
          <div><span className="text-text-muted">{intl.formatMessage({ id: 'employees.password' })}</span> <span className="font-mono font-medium text-text">{shownPassword}</span></div>
        </div>
        <div className="flex gap-2 mt-4">
          <Button size="sm" onClick={onDone}>{intl.formatMessage({ id: 'employees.done' })}</Button>
        </div>
      </div>
    )
  }

  return (
    <div>
      <CardTitle className="mb-3">{intl.formatMessage({ id: 'employees.newEmployee' })}</CardTitle>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Input label={intl.formatMessage({ id: 'employees.fullNameLabel' })} value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder={intl.formatMessage({ id: 'employees.fullNamePlaceholder' })} />
        <Input label={intl.formatMessage({ id: 'employees.headerEmail' })} type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={intl.formatMessage({ id: 'employees.emailPlaceholder' })} />
        <Input
          label={intl.formatMessage({ id: 'employees.passwordLabel' })}
          type="text"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={intl.formatMessage({ id: 'employees.passwordPlaceholder' })}
        />
      </div>
      {passwordTooShort && (
        <p className="text-sm text-danger mt-2">{intl.formatMessage({ id: 'employees.passwordTooShort' })}</p>
      )}
      {create.isError && (
        <p className="text-sm text-danger mt-2">
          {create.error instanceof ApiError ? create.error.body.detail : intl.formatMessage({ id: 'employees.createError' })}
        </p>
      )}
      <div className="flex gap-2 mt-4">
        <Button size="sm" onClick={submit} disabled={create.isPending || !email.trim() || !fullName.trim() || passwordTooShort}>
          {create.isPending ? intl.formatMessage({ id: 'employees.creating' }) : intl.formatMessage({ id: 'employees.createBtn' })}
        </Button>
        <Button size="sm" variant="ghost" onClick={onDone}>{intl.formatMessage({ id: 'employees.cancel' })}</Button>
      </div>
    </div>
  )
}

function AssignCourseForm({ user }: { user: User }) {
  const intl = useIntl()
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
        <label className="block text-sm font-medium text-text mb-1">{intl.formatMessage({ id: 'employees.courseLabel' })}</label>
        <select
          value={courseId}
          onChange={(e) => setCourseId(e.target.value)}
          className="w-full px-3 py-2 text-sm text-text border border-border rounded-lg bg-bg focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/20 transition-colors"
        >
          <option value="">{intl.formatMessage({ id: 'employees.selectCourse' })}</option>
          {courses.map((c) => (
            <option key={c.id} value={c.id}>{c.title}</option>
          ))}
        </select>
      </div>
      <Input label={intl.formatMessage({ id: 'employees.deadlineLabel' })} type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
      {assign.isError && (
        <p className="text-sm text-danger">
          {assign.error instanceof ApiError ? assign.error.body.detail : intl.formatMessage({ id: 'employees.assignError' })}
        </p>
      )}
      {assign.isSuccess && <p className="text-sm text-accent">{intl.formatMessage({ id: 'employees.assignSuccess' })}</p>}
      <Button size="sm" onClick={submit} disabled={!courseId || assign.isPending}>
        {assign.isPending ? intl.formatMessage({ id: 'employees.assigning' }) : intl.formatMessage({ id: 'employees.assignCourse' })}
      </Button>
    </div>
  )
}

function ResetPasswordForm({ employee, onDone }: { employee: User; onDone: () => void }) {
  const intl = useIntl()
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
        <CardTitle className="mb-2">{intl.formatMessage({ id: 'employees.passwordUpdated' })}</CardTitle>
        <p className="text-sm text-text-secondary">
          {intl.formatMessage({ id: 'employees.passwordUpdatedDesc' }, { name: employee.full_name })}
        </p>
        <div className="flex justify-end mt-4">
          <Button size="sm" onClick={onDone}>{intl.formatMessage({ id: 'employees.close' })}</Button>
        </div>
      </div>
    )
  }

  return (
    <div>
      <CardTitle className="mb-3">{intl.formatMessage({ id: 'employees.resetPasswordTitle' })}</CardTitle>
      <p className="text-sm text-text-secondary mb-3">
        {intl.formatMessage({ id: 'employees.newPasswordFor' }, { name: employee.full_name })}
      </p>
      <Input
        label={intl.formatMessage({ id: 'employees.newPasswordLabel' })}
        type="text"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder={intl.formatMessage({ id: 'employees.newPasswordPlaceholder' })}
      />
      {tooShort && (
        <p className="text-sm text-danger mt-2">{intl.formatMessage({ id: 'employees.passwordTooShort6' })}</p>
      )}
      {reset.isError && (
        <p className="text-sm text-danger mt-2">
          {reset.error instanceof ApiError ? reset.error.body.detail : intl.formatMessage({ id: 'employees.resetError' })}
        </p>
      )}
      <div className="flex gap-2 mt-4 justify-end">
        <Button size="sm" variant="ghost" onClick={onDone}>{intl.formatMessage({ id: 'employees.cancel' })}</Button>
        <Button size="sm" onClick={submit} disabled={reset.isPending || !password.trim() || tooShort}>
          {reset.isPending ? intl.formatMessage({ id: 'employees.saving' }) : intl.formatMessage({ id: 'employees.resetBtn' })}
        </Button>
      </div>
    </div>
  )
}

function EmployeeDetail({ employee }: { employee: User }) {
  const intl = useIntl()
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
          {intl.formatMessage({ id: 'employees.resetPassword' })}
        </Button>
      </div>

      <div className="mt-6">
        <CardTitle>{intl.formatMessage({ id: 'employees.assignedCourses' })}</CardTitle>
        <div className="mt-3">
          {isLoading ? (
            <SkeletonRow />
          ) : enrollments.length === 0 ? (
            <p className="text-sm text-text-muted">{intl.formatMessage({ id: 'employees.noAssigned' })}</p>
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
        <CardTitle>{intl.formatMessage({ id: 'employees.assignNewCourse' })}</CardTitle>
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
  const intl = useIntl()
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
  const roleLabel = (role: string) => role === 'admin' ? intl.formatMessage({ id: 'employees.roleAdmin' }) : intl.formatMessage({ id: 'employees.roleEmployee' })

  return (
    <div className="flex flex-col" style={{ maxHeight: 'calc(100vh - 50px - 3rem)' }}>
      <div className="shrink-0 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold text-text">{intl.formatMessage({ id: 'employees.title' })}</h2>
          <p className="text-sm text-text-secondary mt-1">{intl.formatMessage({ id: 'employees.teamCount' }, { count: data?.total ?? employees.length })}</p>
        </div>
        <Button
          variant="primary"
          size="md"
          onClick={(e) => {
            setCreateOrigin(e.currentTarget.getBoundingClientRect())
            setCreating(true)
          }}
        >
          {intl.formatMessage({ id: 'employees.add' })}
        </Button>
      </div>

      <div className="shrink-0 relative mt-4">
        <div className="absolute inset-y-0 left-3 flex items-center pointer-events-none text-text-muted">
          <SearchIcon />
        </div>
        <input
          type="text"
          placeholder={intl.formatMessage({ id: 'employees.searchPlaceholder' })}
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
          <EmptyState title={intl.formatMessage({ id: 'employees.loadError' })} />
        ) : employees.length === 0 ? (
          <EmptyState title={intl.formatMessage({ id: 'employees.emptyTitle' })} description={intl.formatMessage({ id: 'employees.emptyDesc' })} />
        ) : (
          <div className="overflow-x-auto overflow-y-auto flex-1 min-h-0">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10">
                <tr className="border-b border-border bg-bg-subtle">
                  <th className="text-left py-3 px-5 font-medium text-text-secondary rounded-tl-xl">{intl.formatMessage({ id: 'employees.headerName' })}</th>
                  <th className="text-left py-3 px-4 font-medium text-text-secondary">{intl.formatMessage({ id: 'employees.headerEmail' })}</th>
                  <th className="text-left py-3 px-4 font-medium text-text-secondary rounded-tr-xl">{intl.formatMessage({ id: 'employees.headerRole' })}</th>
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
                      <Badge variant="primary" badgeStyle="plain">{roleLabel(emp.role)}</Badge>
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
                  <Badge variant="primary" badgeStyle="plain">{roleLabel(emp.role)}</Badge>
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
