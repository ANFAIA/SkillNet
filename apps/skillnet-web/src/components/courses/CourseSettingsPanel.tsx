import { useEffect, useRef, useState } from 'react'
import { useIntl } from 'react-intl'
import { Button, Card, Select } from '../ui'
import { useUsers } from '../../api/users'
import { useUpdateCourse } from '../../api/courses'
import { useAssignCourse, useDeleteEnrollment, useEnrollments } from '../../api/enrollments'
import { ChoiceList } from '../onboarding/ChoiceList'
import type { CourseRead, ImageSourcePolicy } from '../../types'

type Policy = 'admin' | 'everyone' | 'selected'

export function CourseSettingsPanel({ course }: { course: CourseRead }) {
  const intl = useIntl()
  const updateCourse = useUpdateCourse()
  const assign = useAssignCourse()
  const unassign = useDeleteEnrollment()
  // Explicit `limit`: `useUsers` sends a page size on every call now (default 25) and
  // this panel has no pager. `nameById` below is built from these rows, so a short page
  // does not just hide people — it renders a raw UUID where a name should be.
  const usersQuery = useUsers({ is_active: true, limit: 100 })
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
  const [imagePolicy, setImagePolicyState] = useState<ImageSourcePolicy>(
    course.image_source_policy ?? 'auto',
  )
  const courseIdRef = useRef(course.id)
  useEffect(() => {
    if (courseIdRef.current === course.id) return
    courseIdRef.current = course.id
    setPolicyState((course.artifact_generate_policy ?? 'admin') as Policy)
    setSelected(new Set(course.artifact_generator_ids ?? []))
    setImagePolicyState(course.image_source_policy ?? 'auto')
  }, [
    course.id,
    course.artifact_generate_policy,
    course.artifact_generator_ids,
    course.image_source_policy,
  ])

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

  /**
   * The override over the diagram/screenshot rule. It lives here and NOT in the creation
   * flow on purpose: at creation nobody has seen a lesson yet, so there is nothing to
   * disagree with — the rule decides, and this is where you overrule it afterwards.
   */
  function setImagePolicy(next: ImageSourcePolicy) {
    setImagePolicyState(next)
    updateCourse.mutate({ id: course.id, payload: { image_source_policy: next } })
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
        <h3 className="text-sm font-medium text-text">{intl.formatMessage({ id: 'courseSettings.imagesTitle' })}</h3>
        <p className="mt-1 mb-3 text-xs text-text-muted">{intl.formatMessage({ id: 'courseSettings.imagesHint' })}</p>
        {/* A fieldset rather than a `disabled` prop on every radio: it is the native way
            to freeze a whole group while the save is in flight, and it keeps the group
            semantics the legend gives the options. */}
        <fieldset disabled={saving} className={saving ? 'opacity-60' : undefined}>
          <legend className="sr-only">{intl.formatMessage({ id: 'courseSettings.imagesLabel' })}</legend>
          <ChoiceList
            name={`image-source-policy-${course.id}`}
            value={imagePolicy}
            onSelect={(value) => setImagePolicy(value as ImageSourcePolicy)}
            options={[
              {
                value: 'auto',
                label: intl.formatMessage({ id: 'courseSettings.imagesAuto' }),
                hint: intl.formatMessage({ id: 'courseSettings.imagesAutoHint' }),
              },
              {
                value: 'keep_original',
                label: intl.formatMessage({ id: 'courseSettings.imagesKeep' }),
                hint: intl.formatMessage({ id: 'courseSettings.imagesKeepHint' }),
              },
              {
                value: 'rebuild',
                label: intl.formatMessage({ id: 'courseSettings.imagesRebuild' }),
                hint: intl.formatMessage({ id: 'courseSettings.imagesRebuildHint' }),
              },
            ]}
          />
        </fieldset>
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
