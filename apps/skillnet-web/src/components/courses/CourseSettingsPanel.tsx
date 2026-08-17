import { useEffect, useRef, useState } from 'react'
import { useIntl } from 'react-intl'
import { Button, Card, Select } from '../ui'
import { useUsers } from '../../api/users'
import { useUpdateCourse } from '../../api/courses'
import { useAssignCourse, useDeleteEnrollment, useEnrollments } from '../../api/enrollments'
import type { CourseRead } from '../../types'

type Policy = 'admin' | 'everyone' | 'selected'

export function CourseSettingsPanel({ course }: { course: CourseRead }) {
  const intl = useIntl()
  const updateCourse = useUpdateCourse()
  const assign = useAssignCourse()
  const unassign = useDeleteEnrollment()
  const usersQuery = useUsers({ is_active: true })
  const enrollmentsQuery = useEnrollments({ course_id: course.id })
  const users = usersQuery.data?.items ?? []
  const enrollments = enrollmentsQuery.data?.items ?? []
  const enrolledIds = new Set(enrollments.map((row) => row.user_id))
  const nameById = new Map(users.map((user) => [user.id, user.full_name || user.email]))
  const saving = updateCourse.isPending || assign.isPending || unassign.isPending

  // Local, optimistic source of truth: deriving straight from the (slow to
  // refetch) server state made rapid toggles overwrite each other. We seed from
  // the course and re-seed only when switching courses.
  const [policy, setPolicyState] = useState<Policy>((course.artifact_generate_policy ?? 'admin') as Policy)
  const [selected, setSelected] = useState<Set<string>>(new Set(course.artifact_generator_ids ?? []))
  const courseIdRef = useRef(course.id)
  useEffect(() => {
    if (courseIdRef.current === course.id) return
    courseIdRef.current = course.id
    setPolicyState((course.artifact_generate_policy ?? 'admin') as Policy)
    setSelected(new Set(course.artifact_generator_ids ?? []))
  }, [course.id, course.artifact_generate_policy, course.artifact_generator_ids])

  function setPolicy(next: Policy) {
    setPolicyState(next)
    const ids = next === 'selected' ? [...selected] : []
    if (next !== 'selected') setSelected(new Set())
    updateCourse.mutate({
      id: course.id,
      payload: { artifact_generate_policy: next, artifact_generator_ids: ids },
    })
  }

  function toggleGenerator(userId: string) {
    const next = new Set(selected)
    if (next.has(userId)) next.delete(userId)
    else next.add(userId)
    setSelected(next)
    setPolicyState('selected')
    updateCourse.mutate({
      id: course.id,
      payload: { artifact_generate_policy: 'selected', artifact_generator_ids: [...next] },
    })
  }

  function addEnrollment(userId: string) {
    if (!userId || enrolledIds.has(userId)) return
    assign.mutate({ user_ids: [userId], course_id: course.id })
  }

  return (
    <div className="mb-6 grid gap-4 md:grid-cols-2">
      <Card>
        <h3 className="text-sm font-medium text-text">{intl.formatMessage({ id: 'courseSettings.generateTitle' })}</h3>
        <p className="mt-1 mb-3 text-xs text-text-muted">{intl.formatMessage({ id: 'courseSettings.generateHint' })}</p>
        <Select
          label={intl.formatMessage({ id: 'courseSettings.generateLabel' })}
          hideLabel
          value={policy}
          disabled={saving}
          onChange={(event) => setPolicy(event.target.value as Policy)}
        >
          <option value="admin">{intl.formatMessage({ id: 'courseSettings.generateAdmin' })}</option>
          <option value="everyone">{intl.formatMessage({ id: 'courseSettings.generateEveryone' })}</option>
          <option value="selected">{intl.formatMessage({ id: 'courseSettings.generateSelected' })}</option>
        </Select>
        {policy === 'selected' && (
          <ul className="mt-3 max-h-48 space-y-1 overflow-y-auto">
            {users.map((user) => (
              <li key={user.id}>
                <label className="flex cursor-pointer items-center gap-2 rounded-md px-1 py-1 text-sm text-text hover:bg-bg-muted">
                  <input
                    type="checkbox"
                    checked={selected.has(user.id)}
                    disabled={saving}
                    onChange={() => toggleGenerator(user.id)}
                  />
                  <span className="min-w-0 truncate">{user.full_name || user.email}</span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <h3 className="text-sm font-medium text-text">{intl.formatMessage({ id: 'courseSettings.assignTitle' })}</h3>
        <p className="mt-1 mb-3 text-xs text-text-muted">{intl.formatMessage({ id: 'courseSettings.assignHint' })}</p>
        {enrollments.length === 0 ? (
          <p className="mb-3 text-sm text-text-muted">{intl.formatMessage({ id: 'courseSettings.assignEmpty' })}</p>
        ) : (
          <ul className="mb-3 max-h-40 space-y-1 overflow-y-auto">
            {enrollments.map((row) => (
              <li key={row.id} className="flex items-center justify-between gap-2 text-sm">
                <span className="min-w-0 truncate text-text">{nameById.get(row.user_id) ?? row.user_id}</span>
                <Button variant="ghost" size="sm" disabled={saving} onClick={() => unassign.mutate(row.id)}>
                  {intl.formatMessage({ id: 'courseSettings.unassign' })}
                </Button>
              </li>
            ))}
          </ul>
        )}
        <Select
          label={intl.formatMessage({ id: 'courseSettings.assignAdd' })}
          hideLabel
          value=""
          disabled={saving}
          onChange={(event) => addEnrollment(event.target.value)}
        >
          <option value="">{intl.formatMessage({ id: 'courseSettings.assignAdd' })}</option>
          {users.filter((user) => !enrolledIds.has(user.id)).map((user) => (
            <option key={user.id} value={user.id}>{user.full_name || user.email}</option>
          ))}
        </Select>
      </Card>
    </div>
  )
}
