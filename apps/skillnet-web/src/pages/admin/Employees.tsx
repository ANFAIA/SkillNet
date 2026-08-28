import { useDeferredValue, useState } from 'react'
import { useIntl } from 'react-intl'
import { motion } from 'framer-motion'
import { Badge, Button, Card, CardTitle, EmptyState, Input, Modal, PageHeader, Pager, SearchField, Select, SkeletonRow } from '../../components/ui'
import { useUsers, USERS_PAGE_SIZE, useCreateUser, useResetPassword, useSetEmployeeActive, useSetUserRole } from '../../api/users'
import { useUserGroups, type UserGroup } from '../../api/user-groups'
import { UserGroupSidebar, type GroupFilter } from '../../components/people/UserGroupSidebar'
import { GroupMembersDialog } from '../../components/people/GroupMembersDialog'
import { AssignToGroupDialog } from '../../components/people/AssignToGroupDialog'
import { PersonGroupsSection } from '../../components/people/PersonGroupsSection'
import { useCourses } from '../../api/courses'
import { useCourseFolders } from '../../api/course-folders'
import { useAssignCourse, useAssignFolder, useDeleteEnrollment, useEnrollments } from '../../api/enrollments'
import { ApiError } from '../../api/client'
import { staggerContainer, staggerItem } from '../../lib/motion'
import type { EnrollmentRead, User, UserGroupBrief } from '../../types'

function CreateEmployeeForm({ onDone }: { onDone: () => void }) {
  const intl = useIntl()
  const create = useCreateUser()
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<'admin' | 'employee'>('employee')

  const created = create.data
  const passwordTooShort = password.length > 0 && password.length < 8

  function submit() {
    if (!email.trim() || !fullName.trim() || passwordTooShort || create.isPending) return
    create.mutate({
      email: email.trim(),
      full_name: fullName.trim(),
      password: password.trim() || undefined,
      role,
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
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={intl.formatMessage({ id: 'employees.passwordPlaceholder' })}
        />
        <Select
          label={intl.formatMessage({ id: 'employees.roleLabel' })}
          value={role}
          onChange={(e) => setRole(e.target.value as 'admin' | 'employee')}
        >
          <option value="employee">{intl.formatMessage({ id: 'employees.roleEmployee' })}</option>
          <option value="admin">{intl.formatMessage({ id: 'employees.roleAdmin' })}</option>
        </Select>
      </div>
      <p className="text-sm text-text-muted mt-2">
        {role === 'admin'
          ? intl.formatMessage({ id: 'employees.roleAdminHint' })
          : intl.formatMessage({ id: 'employees.roleEmployeeHint' })}
      </p>
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

/** One course, or every published course of one library folder. */
type AssignMode = 'course' | 'folder'

/**
 * Assign training to one person, from their own record.
 *
 * The record could only ever assign a single course, one click at a time, while the
 * library screen could already assign a whole folder to many people. Onboarding is a
 * folder and hiring happens one person at a time, so the missing direction was the one
 * that gets used: this is it.
 *
 * The two modes are separate components rather than one form with two branches, so each
 * owns only the queries it needs — in course mode nothing asks the server about folders.
 */
function AssignTrainingForm({ user }: { user: User }) {
  const intl = useIntl()
  const [mode, setMode] = useState<AssignMode>('course')

  return (
    <div className="mt-3 space-y-3">
      <Select
        label={intl.formatMessage({
          id: 'employees.assignModeLabel',
          defaultMessage: 'Qué quieres asignar',
        })}
        value={mode}
        onChange={(e) => setMode(e.target.value as AssignMode)}
      >
        <option value="course">
          {intl.formatMessage({ id: 'employees.assignModeCourse', defaultMessage: 'Un curso' })}
        </option>
        <option value="folder">
          {intl.formatMessage({ id: 'employees.assignModeFolder', defaultMessage: 'Una carpeta completa' })}
        </option>
      </Select>
      {mode === 'course' ? <AssignSingleCourse user={user} /> : <AssignFolder user={user} />}
    </div>
  )
}

function AssignSingleCourse({ user }: { user: User }) {
  const intl = useIntl()
  const [search, setSearch] = useState('')
  // Deferred and not one request per keystroke: `GET /courses` searches server-side.
  // The employee search below does the same, and `pages/admin/Content.tsx` is where the
  // pattern comes from.
  const deferredSearch = useDeferredValue(search.trim())
  const { data: courseData } = useCourses({
    status: 'published',
    search: deferredSearch || undefined,
  })
  const assign = useAssignCourse()
  const [courseId, setCourseId] = useState('')
  const [deadline, setDeadline] = useState('')
  const courses = courseData?.items ?? []
  // `limit` is capped at 100 by the server, so in a library bigger than that the tail of
  // the list is only reachable through the search box. A dropdown that silently stops at
  // course 100 makes those courses unassignable and says nothing; this says it.
  const hiddenByThePage = (courseData?.total ?? 0) > courses.length

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
    <div className="space-y-3">
      <SearchField
        label={intl.formatMessage({
          id: 'employees.courseSearchLabel',
          defaultMessage: 'Buscar curso por nombre',
        })}
        placeholder={intl.formatMessage({
          id: 'employees.courseSearchLabel',
          defaultMessage: 'Buscar curso por nombre',
        })}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <Select
        label={intl.formatMessage({ id: 'employees.courseLabel' })}
        value={courseId}
        onChange={(e) => setCourseId(e.target.value)}
      >
        <option value="">{intl.formatMessage({ id: 'employees.selectCourse' })}</option>
        {courses.map((c) => (
          <option key={c.id} value={c.id}>{c.title}</option>
        ))}
      </Select>
      {hiddenByThePage && (
        <p className="text-xs text-text-muted">
          {intl.formatMessage(
            {
              id: 'employees.courseListTruncated',
              defaultMessage: 'Se muestran {shown} de {total} cursos publicados. Busca por nombre para llegar al resto.',
            },
            { shown: courses.length, total: courseData?.total ?? 0 },
          )}
        </p>
      )}
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

function AssignFolder({ user }: { user: User }) {
  const intl = useIntl()
  const folders = useCourseFolders()
  const assign = useAssignFolder()
  const [folderId, setFolderId] = useState('')
  const [deadline, setDeadline] = useState('')
  // A folder's own `course_count` counts drafts too, and only PUBLISHED courses are ever
  // enrolled (`list_published_course_ids`). So the number shown before the click has to
  // come from the same filter the server will apply: one page of one, read for `total`.
  const published = useCourses({
    status: 'published',
    folderId: folderId || undefined,
    limit: 1,
  })
  const publishedCount = folderId ? published.data?.total ?? 0 : 0
  const nothingToAssign = !!folderId && !published.isLoading && publishedCount === 0
  const result = assign.data

  function pickFolder(next: string) {
    setFolderId(next)
    // The previous folder's outcome must not stand next to another folder's name.
    assign.reset()
  }

  function submit() {
    if (!folderId || nothingToAssign || assign.isPending) return
    assign.mutate({ user_ids: [user.id], folder_id: folderId, deadline: deadline || undefined })
  }

  return (
    <div className="space-y-3">
      <Select
        label={intl.formatMessage({ id: 'employees.folderLabel', defaultMessage: 'Carpeta' })}
        value={folderId}
        onChange={(e) => pickFolder(e.target.value)}
      >
        <option value="">
          {intl.formatMessage({ id: 'employees.selectFolder', defaultMessage: 'Selecciona una carpeta' })}
        </option>
        {(folders.data ?? []).map((folder) => (
          <option key={folder.id} value={folder.id}>{folder.name}</option>
        ))}
      </Select>
      {!folders.isLoading && (folders.data ?? []).length === 0 && (
        <p className="text-sm text-text-muted">
          {intl.formatMessage({
            id: 'employees.foldersEmpty',
            defaultMessage: 'Todavía no hay carpetas en la biblioteca.',
          })}
        </p>
      )}
      {!!folderId && !published.isLoading && (
        nothingToAssign ? (
          // Assigning this folder would return 200 and enrol nobody. Saying it here is
          // the whole point: the old silence looked exactly like success.
          <p className="text-sm text-danger">
            {intl.formatMessage({
              id: 'employees.folderNothingPublished',
              defaultMessage: 'Esta carpeta no tiene ningún curso publicado, así que asignarla no matricularía en nada. Publica sus cursos primero.',
            })}
          </p>
        ) : (
          <p className="text-xs text-text-muted">
            {intl.formatMessage(
              {
                id: 'employees.folderPublishedCount',
                defaultMessage: '{count, plural, one {Se asignará 1 curso publicado} other {Se asignarán # cursos publicados}}.',
              },
              { count: publishedCount },
            )}
          </p>
        )
      )}
      <Input label={intl.formatMessage({ id: 'employees.deadlineLabel' })} type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
      {assign.isError && (
        <p className="text-sm text-danger">
          {assign.error instanceof ApiError ? assign.error.body.detail : intl.formatMessage({ id: 'content.assignFolderError' })}
        </p>
      )}
      {result && (
        <div className="text-sm">
          <p className="text-accent">
            {intl.formatMessage(
              { id: 'content.assignFolderSuccess' },
              { enrollments: result.created_count, courses: result.course_count },
            )}
          </p>
          {result.skipped_existing_count > 0 && (
            <p className="mt-1 text-text-muted">
              {intl.formatMessage(
                { id: 'content.assignFolderSkipped' },
                { count: result.skipped_existing_count },
              )}
            </p>
          )}
        </div>
      )}
      <Button size="sm" onClick={submit} disabled={!folderId || nothingToAssign || assign.isPending}>
        {assign.isPending
          ? intl.formatMessage({ id: 'employees.assigning' })
          : intl.formatMessage({ id: 'employees.assignFolderBtn', defaultMessage: 'Asignar la carpeta' })}
      </Button>
    </div>
  )
}

function ResetPasswordForm({ employee, onDone }: { employee: User; onDone: () => void }) {
  const intl = useIntl()
  const [password, setPassword] = useState('')
  const reset = useResetPassword()
  const tooShort = password.length > 0 && password.length < 8

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
        type="password"
        autoComplete="new-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder={intl.formatMessage({ id: 'employees.newPasswordPlaceholder' })}
      />
      {tooShort && (
        <p className="text-sm text-danger mt-2">{intl.formatMessage({ id: 'employees.passwordTooShort' })}</p>
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

/**
 * Whether the server will let this enrollment be removed.
 *
 * `enrollment_service.delete` refuses anything that is not `assigned` with a 409 ("only
 * assigned (not started) enrollments can be removed"), so the action is not offered for
 * the rest. Written as "neither started nor finished" rather than `=== 'assigned'`
 * because the API sends `assigned` for that state while `EnrollmentStatus` in
 * `types/index.ts` still spells it `not_started`: matching either name alone would be
 * wrong about the other, and both agree on the two states listed here.
 */
function canRemoveEnrollment(enrollment: EnrollmentRead): boolean {
  return enrollment.status !== 'in_progress' && enrollment.status !== 'completed'
}

function EmployeeDetail({ employee }: { employee: User }) {
  const intl = useIntl()
  const { data: enrollmentData, isLoading } = useEnrollments({ user_id: employee.id })
  const enrollments = enrollmentData?.items ?? []
  const [showResetPw, setShowResetPw] = useState(false)
  const setActive = useSetEmployeeActive()
  const setRole = useSetUserRole()
  const removeEnrollment = useDeleteEnrollment()
  const [removeError, setRemoveError] = useState<string | null>(null)
  const isActive = employee.is_active !== false
  const isAdmin = employee.role === 'admin'

  function remove(enrollment: EnrollmentRead) {
    if (
      !window.confirm(
        intl.formatMessage(
          {
            id: 'employees.removeCourseConfirm',
            defaultMessage: '¿Quitar “{course}” de los cursos de {name}?',
          },
          { course: enrollment.course_title, name: employee.full_name },
        ),
      )
    ) {
      return
    }
    setRemoveError(null)
    removeEnrollment.mutate(enrollment.id, {
      onError: (error) => {
        // A 409 here means the person started the course between this list being
        // fetched and the click. The server's message is English-only, so it is
        // translated instead of shown.
        setRemoveError(
          error instanceof ApiError && error.status === 409
            ? intl.formatMessage(
                {
                  id: 'employees.removeCourseStarted',
                  defaultMessage: 'Ya no se puede quitar: {name} empezó el curso. Solo se pueden quitar cursos sin empezar.',
                },
                { name: employee.full_name },
              )
            : intl.formatMessage({
                id: 'employees.removeCourseError',
                defaultMessage: 'No se pudo quitar el curso.',
              }),
        )
      },
    })
  }

  function toggleRole() {
    const next = isAdmin ? 'employee' : 'admin'
    if (
      !window.confirm(
        intl.formatMessage(
          { id: next === 'admin' ? 'employees.promoteConfirm' : 'employees.demoteConfirm' },
          { name: employee.full_name },
        ),
      )
    ) {
      return
    }
    setRole.mutate({ userId: employee.id, role: next })
  }

  function toggleActive() {
    const next = !isActive
    if (
      !next &&
      !window.confirm(
        intl.formatMessage({ id: 'employees.deactivateConfirm' }, { name: employee.full_name }),
      )
    ) {
      return
    }
    setActive.mutate({ userId: employee.id, isActive: next })
  }

  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 pr-8">
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-semibold text-text truncate">{employee.full_name}</h3>
            {!isActive && (
              <Badge variant="danger" badgeStyle="plain">
                {intl.formatMessage({ id: 'employees.statusInactive' })}
              </Badge>
            )}
          </div>
          <p className="text-sm text-text-secondary truncate">{employee.email}</p>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button size="sm" variant="ghost" onClick={() => setShowResetPw(true)}>
            {intl.formatMessage({ id: 'employees.resetPassword' })}
          </Button>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          size="sm"
          variant={isActive ? 'secondary' : 'primary'}
          onClick={toggleActive}
          disabled={setActive.isPending}
        >
          {isActive
            ? intl.formatMessage({ id: 'employees.deactivate' })
            : intl.formatMessage({ id: 'employees.reactivate' })}
        </Button>
        <Button size="sm" variant="secondary" onClick={toggleRole} disabled={setRole.isPending}>
          {isAdmin
            ? intl.formatMessage({ id: 'employees.demoteToEmployee' })
            : intl.formatMessage({ id: 'employees.promoteToAdmin' })}
        </Button>
      </div>
      {/* The server owns both safeguards (last admin, cross-organization), so its
          message is the one shown — the UI never second-guesses which rule fired. */}
      {setActive.isError && (
        <p className="text-sm text-danger mt-2">
          {setActive.error instanceof ApiError
            ? setActive.error.body.detail
            : intl.formatMessage({ id: 'employees.statusUpdateError' })}
        </p>
      )}
      {setRole.isError && (
        <p className="text-sm text-danger mt-2">
          {setRole.error instanceof ApiError
            ? setRole.error.body.detail
            : intl.formatMessage({ id: 'employees.roleUpdateError' })}
        </p>
      )}

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
                  <div className="flex shrink-0 items-center gap-2 ml-4">
                    {/* `progress` is a 0..1 fraction on the wire, like every learner
                        screen reads it. Printed raw it showed "0.5%" for half a course. */}
                    <span className="text-xs text-text-muted">{Math.round((e.progress ?? 0) * 100)}%</span>
                    {canRemoveEnrollment(e) && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => remove(e)}
                        disabled={removeEnrollment.isPending}
                      >
                        {intl.formatMessage({ id: 'courseSettings.unassign' })}
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
          {removeError && <p className="mt-2 text-sm text-danger">{removeError}</p>}
        </div>
      </div>

      <div className="mt-5 border-t border-border pt-5">
        <CardTitle className="mb-3">{intl.formatMessage({ id: 'groups.personTitle' })}</CardTitle>
        <PersonGroupsSection person={employee} />
      </div>

      <div className="mt-5 border-t border-border pt-5">
        <CardTitle>{intl.formatMessage({ id: 'employees.assignNewCourse' })}</CardTitle>
        <AssignTrainingForm user={employee} />
      </div>

      {showResetPw && (
        <Modal open={showResetPw} onClose={() => setShowResetPw(false)} size="sm">
          <ResetPasswordForm employee={employee} onDone={() => setShowResetPw(false)} />
        </Modal>
      )}
    </div>
  )
}

/**
 * Which group a person belongs to, as one field of their row.
 *
 * One name, plainly: belonging to a single group is the normal case, and it reads as a
 * fact about the person rather than as a collection. The `+N` is the valve for the rare
 * second membership — orthogonal axes like a shift and a branch office are legitimate,
 * so the model stays many-to-many — and it never becomes the shape of the cell. The
 * whole list lives on the person's record (`PersonGroupsSection`), which is where
 * somebody who cares about all of them is already looking.
 *
 * The name filters the table by that group: the same state the rail writes, so the
 * screen has one notion of "showing this group" and not two. A column that only labelled
 * would take a column's worth of width to answer nothing.
 */
function PersonGroupCell({ groups, onFilter }: { groups: UserGroupBrief[]; onFilter: (id: string) => void }) {
  const intl = useIntl()
  if (groups.length === 0) {
    // A dash, not a sentence: the empty case is common and must not shout. The label
    // beside it is for screen readers, which would otherwise announce "em dash".
    return (
      <>
        <span aria-hidden="true" className="text-text-muted">—</span>
        <span className="sr-only">{intl.formatMessage({ id: 'employees.groupNone' })}</span>
      </>
    )
  }
  const [first, ...rest] = groups
  const alsoIn = intl.formatMessage(
    { id: 'employees.groupAlsoIn' },
    { names: rest.map((g) => g.name).join(', ') },
  )
  return (
    // The cap lives here and not on the `<td>`: the table lays out `auto`, where a
    // `max-width` on a cell is advisory, so a 90-character group name would widen the
    // column instead of ellipsing.
    <span className="inline-flex max-w-48 min-w-0 items-baseline gap-1.5">
      <button
        type="button"
        title={intl.formatMessage({ id: 'employees.groupFilter' }, { name: first.name })}
        // The row itself opens the person's record. Without this the filter would never
        // run: the click would reach the row and open the modal instead.
        onClick={(event) => {
          event.stopPropagation()
          onFilter(first.id)
        }}
        className="truncate text-primary hover:underline"
      >
        {first.name}
      </button>
      {rest.length > 0 && (
        <span className="shrink-0 text-xs text-text-muted" title={alsoIn}>
          {intl.formatMessage({ id: 'employees.groupOverflow' }, { count: rest.length })}
          <span className="sr-only"> {alsoIn}</span>
        </span>
      )}
    </span>
  )
}

export function Employees() {
  const intl = useIntl()
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<User | null>(null)
  const [creating, setCreating] = useState(false)
  const [roleFilter, setRoleFilter] = useState('')
  const [activeFilter, setActiveFilter] = useState('')
  const [group, setGroup] = useState<GroupFilter>('all')
  const [offset, setOffset] = useState(0)
  const [managingMembers, setManagingMembers] = useState<UserGroup | null>(null)
  const [assigningGroup, setAssigningGroup] = useState<UserGroup | null>(null)
  const [createOrigin, setCreateOrigin] = useState<DOMRect | null>(null)
  const [detailOrigin, setDetailOrigin] = useState<DOMRect | null>(null)
  // The box stays instant; the query lags one keystroke behind instead of firing a
  // request per character. Same treatment as the course library's search.
  const deferredSearch = useDeferredValue(search.trim())
  // No hardcoded `role: 'employee'` any more: administrators are members of the
  // organization too, and a list that hides them makes it impossible to see who can
  // change roles — or to demote anyone.
  //
  // Every filter, including the group, is a query parameter. Narrowing the fetched page
  // in the browser would only ever find the people who happened to be on it — and the
  // page is now explicitly one page, which is the whole point of this screen's rewrite.
  const { data, isLoading, error } = useUsers({
    role: roleFilter || undefined,
    search: deferredSearch || undefined,
    is_active: activeFilter === '' ? undefined : activeFilter === 'active',
    group_id: group === 'all' || group === 'ungrouped' ? undefined : group,
    ungrouped: group === 'ungrouped',
    // Always asked for, never made to depend on `orgHasGroups` below. Flipping this
    // flag once the group count lands would change the query key and fetch the same
    // page twice — the column is meant to cost one read, not to look like it does.
    // An organization with no groups answers the join with nothing.
    with_groups: true,
    offset,
    limit: USERS_PAGE_SIZE,
  })
  // The rail's two counts, and nothing else: one row asked for, read for its `total`.
  const orgTotal = useUsers({ limit: 1 })
  const ungroupedTotal = useUsers({ ungrouped: true, limit: 1 })
  // Does this organization have groups at all? Same one-row probe as the two counts
  // above, read for its `total`. Without groups the column would be a header and a
  // column of dashes, so it is not drawn — and this is the only read that can say so:
  // a page where nobody is in a group looks identical either way.
  const groupsTotal = useUserGroups({ limit: 1 })
  const orgHasGroups = (groupsTotal.data?.total ?? 0) > 0

  function openDetail(emp: User, e: { currentTarget: Element }) {
    setDetailOrigin(e.currentTarget.getBoundingClientRect())
    setSelected(emp)
  }

  /** Any filter change invalidates the current page number, so it goes back to the first. */
  function refilter(apply: () => void) {
    apply()
    setOffset(0)
  }

  const employees = data?.items ?? []
  const total = data?.total ?? 0
  const hasFilters = !!roleFilter || !!activeFilter || group !== 'all' || search.trim().length > 0
  const roleLabel = (role: string) => role === 'admin' ? intl.formatMessage({ id: 'employees.roleAdmin' }) : intl.formatMessage({ id: 'employees.roleEmployee' })

  return (
    <div>
      <PageHeader
        title={intl.formatMessage({ id: 'employees.title' })}
        description={intl.formatMessage({ id: 'employees.teamCount' }, { count: orgTotal.data?.total ?? total })}
        actions={(
          <Button
            variant="primary"
            size="md"
            onClick={(event) => {
              setCreateOrigin(event.currentTarget.getBoundingClientRect())
              setCreating(true)
            }}
          >
            {intl.formatMessage({ id: 'employees.add' })}
          </Button>
        )}
      />

      {/* Wider than the library's 220px folder rail on purpose: a group row carries four
          actions to the folder's three, and at 220px the hovered name was clipped to
          "Turno d" with its member count hidden behind the buttons. */}
      <div className="mt-5 grid gap-5 xl:grid-cols-[264px_minmax(0,1fr)]">
        <div>
          {/* The rail owns its own query, search box and page number: they are its state,
              and a screen holding them would only be a longer way of saying the same
              thing. Its loading and error states live inside it too, so the two virtual
              rows keep working while the paged part of the list is still arriving. */}
          <UserGroupSidebar
            selected={group}
            totalCount={orgTotal.data?.total ?? 0}
            ungroupedCount={ungroupedTotal.data?.total ?? 0}
            onSelect={(value) => refilter(() => setGroup(value))}
            onManageMembers={setManagingMembers}
            onAssign={setAssigningGroup}
          />
        </div>

        <section className="min-w-0" aria-label={intl.formatMessage({ id: 'employees.title' })}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <SearchField
            label={intl.formatMessage({ id: 'employees.searchPlaceholder' })}
            placeholder={intl.formatMessage({ id: 'employees.searchPlaceholder' })}
            value={search}
            onChange={(e) => refilter(() => setSearch(e.target.value))}
            className="flex-1"
        />
        <Select
          label={intl.formatMessage({ id: 'employees.filterRoleLabel' })}
          value={roleFilter}
          onChange={(e) => refilter(() => setRoleFilter(e.target.value))}
          className="sm:w-44"
        >
          <option value="">{intl.formatMessage({ id: 'employees.filterRoleAll' })}</option>
          <option value="admin">{intl.formatMessage({ id: 'employees.roleAdmin' })}</option>
          <option value="employee">{intl.formatMessage({ id: 'employees.roleEmployee' })}</option>
        </Select>
        <Select
          label={intl.formatMessage({ id: 'employees.filterStatusLabel' })}
          value={activeFilter}
          onChange={(e) => refilter(() => setActiveFilter(e.target.value))}
          className="sm:w-44"
        >
          <option value="">{intl.formatMessage({ id: 'employees.filterStatusAll' })}</option>
          <option value="active">{intl.formatMessage({ id: 'employees.filterStatusActive' })}</option>
          <option value="inactive">{intl.formatMessage({ id: 'employees.statusInactive' })}</option>
        </Select>
      </div>

      <div className="mt-3 flex items-center justify-end gap-3 min-h-6">
        {hasFilters && (
          <button
            type="button"
            onClick={() => refilter(() => { setSearch(''); setRoleFilter(''); setActiveFilter(''); setGroup('all') })}
            className="text-xs font-medium text-primary hover:text-primary-hover"
          >
            {intl.formatMessage({ id: 'content.clearFilters' })}
          </button>
        )}
      </div>

      {/* Desktop table */}
      <Card className="mt-2 hidden overflow-hidden p-0 md:block">
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
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10">
                <tr className="border-b border-border bg-bg-subtle">
                  <th className="text-left py-3 px-5 font-medium text-text-secondary rounded-tl-xl">{intl.formatMessage({ id: 'employees.headerName' })}</th>
                  <th className="text-left py-3 px-4 font-medium text-text-secondary">{intl.formatMessage({ id: 'employees.headerEmail' })}</th>
                  {/* Singular: one group is the normal case, and a plural header would
                      promise a list the cell deliberately does not draw. */}
                  {orgHasGroups && (
                    <th className="text-left py-3 px-4 font-medium text-text-secondary">{intl.formatMessage({ id: 'employees.headerGroup' })}</th>
                  )}
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
                    <td className="py-3 px-5">
                      <span className="font-medium text-text">{emp.full_name}</span>
                      {emp.is_active === false && (
                        <Badge variant="danger" badgeStyle="plain" className="ml-2">
                          {intl.formatMessage({ id: 'employees.statusInactive' })}
                        </Badge>
                      )}
                    </td>
                    <td className="py-3 px-4 text-text-secondary">{emp.email}</td>
                    {orgHasGroups && (
                      <td className="py-3 px-4">
                        <PersonGroupCell
                          groups={emp.groups ?? []}
                          onFilter={(id) => refilter(() => setGroup(id))}
                        />
                      </td>
                    )}
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
                    <div className="flex items-center gap-2">
                      <p className="font-medium text-text truncate">{emp.full_name}</p>
                      {emp.is_active === false && (
                        <Badge variant="danger" badgeStyle="plain">
                          {intl.formatMessage({ id: 'employees.statusInactive' })}
                        </Badge>
                      )}
                    </div>
                    <p className="text-sm text-text-secondary mt-0.5 truncate">{emp.email}</p>
                    {/* Below `md` the table is `display: none`, so without this line the
                        group simply does not exist on a phone. */}
                    {orgHasGroups && (
                      <p className="mt-1 text-sm">
                        <PersonGroupCell
                          groups={emp.groups ?? []}
                          onFilter={(id) => refilter(() => setGroup(id))}
                        />
                      </p>
                    )}
                  </div>
                  <Badge variant="primary" badgeStyle="plain">{roleLabel(emp.role)}</Badge>
                </div>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      )}

      {/* The range also sits above the table, next to "clear filters", because that is
          where the result count belongs; here it is the second half of the same line. */}
      <Pager
        className="mt-4"
        offset={offset}
        shown={employees.length}
        total={total}
        pageSize={USERS_PAGE_SIZE}
        disabled={isLoading}
        onChange={setOffset}
      />
        </section>
      </div>

      {/* Create-employee modal */}
      <Modal open={creating} onClose={() => setCreating(false)} size="lg" origin={createOrigin}>
        <CreateEmployeeForm onDone={() => setCreating(false)} />
      </Modal>

      {/* Employee-detail modal */}
      <Modal open={!!selected} onClose={() => setSelected(null)} size="md" origin={detailOrigin}>
        {selected && <EmployeeDetail employee={selected} />}
      </Modal>

      {managingMembers && (
        <GroupMembersDialog group={managingMembers} onClose={() => setManagingMembers(null)} />
      )}
      {assigningGroup && (
        <AssignToGroupDialog group={assigningGroup} onClose={() => setAssigningGroup(null)} />
      )}
    </div>
  )
}
