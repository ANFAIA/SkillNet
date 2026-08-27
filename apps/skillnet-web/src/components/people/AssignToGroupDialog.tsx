import { useDeferredValue, useState } from 'react'
import { useIntl } from 'react-intl'
import { ApiError } from '../../api/client'
import { useCourseFolders } from '../../api/course-folders'
import { useCourses } from '../../api/courses'
import {
  useAssignToGroups,
  type EnrollmentAssignmentResult,
} from '../../api/enrollments'
import type { UserGroup } from '../../api/user-groups'
import { Button, Input, Modal, Select } from '../ui'

interface AssignToGroupDialogProps {
  group: UserGroup
  onClose: () => void
}

type Target = { kind: 'course' | 'folder'; id: string }

/**
 * Assign one course, or one whole folder, to every member of a group.
 *
 * The request carries `group_ids: [group.id]` and **no people at all**. The server
 * resolves the membership, which is the only place that can be done correctly: the
 * browser holds one page of members at most, and `user_ids` is capped at 100 anyway.
 *
 * Two things this says before the button is pressed, because both used to be discovered
 * afterwards as a zero that looked like success:
 *
 * * a folder assigns its **published** courses only, so a folder of drafts enrols
 *   nobody — the count comes from the same filter the server will apply;
 * * a group whose members are all deactivated enrols nobody either, and the result
 *   reports that separately from "everybody already had it".
 */
export function AssignToGroupDialog({ group, onClose }: AssignToGroupDialogProps) {
  const intl = useIntl()
  const assign = useAssignToGroups()
  const folders = useCourseFolders()
  const [target, setTarget] = useState<Target | null>(null)
  const [deadline, setDeadline] = useState('')
  const [search, setSearch] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<EnrollmentAssignmentResult | null>(null)

  // Published only: an unpublished course cannot be enrolled, so offering one would be
  // offering an action that answers 200 and does nothing. The term is deferred so the box
  // stays instant and the query lags a keystroke instead of firing per character.
  const deferredSearch = useDeferredValue(search.trim())
  const courses = useCourses({ status: 'published', search: deferredSearch || undefined, limit: 50 })
  const courseItems = courses.data?.items ?? []
  const hiddenCourses = Math.max(0, (courses.data?.total ?? 0) - courseItems.length)

  // How many published courses the chosen folder holds — `course_count` on the folder
  // counts drafts too, so it is the wrong number to show here.
  const folderPublished = useCourses({
    status: 'published',
    folderId: target?.kind === 'folder' ? target.id : undefined,
    limit: 1,
  })
  const publishedInFolder = target?.kind === 'folder' ? folderPublished.data?.total ?? 0 : 0
  const emptyFolder =
    target?.kind === 'folder' && !folderPublished.isLoading && publishedInFolder === 0

  function pick(next: Target | null) {
    setTarget(next)
    // A previous outcome must not sit next to a different target's name.
    setResult(null)
    setError(null)
  }

  async function submit() {
    if (!target || emptyFolder || assign.isPending) return
    setError(null)
    try {
      setResult(
        await assign.mutateAsync({
          group_ids: [group.id],
          ...(target.kind === 'course' ? { course_id: target.id } : { folder_id: target.id }),
          deadline: deadline || undefined,
        }),
      )
    } catch (reason) {
      setError(reason instanceof ApiError ? reason.body.detail : intl.formatMessage({ id: 'groups.assignError' }))
    }
  }

  return (
    <Modal open onClose={onClose} size="md">
      <h2 className="text-lg font-semibold text-text">
        {intl.formatMessage({ id: 'groups.assignTitle' }, { name: group.name })}
      </h2>
      <p className="mt-1 text-sm text-text-secondary">
        {intl.formatMessage({ id: 'groups.assignDescription' }, { count: group.member_count })}
      </p>

      {result ? (
        <div className="mt-5 space-y-1 text-sm">
          <p className="text-text">
            {intl.formatMessage(
              { id: 'groups.assignSuccess' },
              { enrollments: result.created_count, people: result.person_count, courses: result.course_count },
            )}
          </p>
          {result.course_count === 0 && (
            <p className="text-warning">{intl.formatMessage({ id: 'groups.assignNoPublished' })}</p>
          )}
          {result.person_count === 0 && result.course_count > 0 && (
            <p className="text-warning">{intl.formatMessage({ id: 'groups.assignNobody' })}</p>
          )}
          {result.skipped_existing_count > 0 && (
            <p className="text-text-muted">
              {intl.formatMessage({ id: 'content.assignFolderSkipped' }, { count: result.skipped_existing_count })}
            </p>
          )}
          {result.skipped_inactive_count > 0 && (
            <p className="text-text-muted">
              {intl.formatMessage({ id: 'groups.assignSkippedInactive' }, { count: result.skipped_inactive_count })}
            </p>
          )}
          <Button className="mt-4" onClick={onClose}>{intl.formatMessage({ id: 'groups.close' })}</Button>
        </div>
      ) : (
        <>
          <div className="mt-5 space-y-3">
            <Select
              label={intl.formatMessage({ id: 'groups.assignFolderLabel' })}
              value={target?.kind === 'folder' ? target.id : ''}
              onChange={(event) => pick(event.target.value ? { kind: 'folder', id: event.target.value } : null)}
            >
              <option value="">{intl.formatMessage({ id: 'groups.assignPickFolder' })}</option>
              {(folders.data ?? []).map((folder) => (
                <option key={folder.id} value={folder.id}>{folder.name}</option>
              ))}
            </Select>

            <Input
              label={intl.formatMessage({ id: 'groups.assignCourseSearch' })}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={intl.formatMessage({ id: 'groups.assignCourseSearch' })}
            />
            <Select
              label={intl.formatMessage({ id: 'groups.assignCourseLabel' })}
              value={target?.kind === 'course' ? target.id : ''}
              onChange={(event) => pick(event.target.value ? { kind: 'course', id: event.target.value } : null)}
            >
              <option value="">{intl.formatMessage({ id: 'groups.assignPickCourse' })}</option>
              {courseItems.map((course) => (
                <option key={course.id} value={course.id}>{course.title}</option>
              ))}
            </Select>
            {hiddenCourses > 0 && (
              <p className="text-xs text-text-muted">
                {intl.formatMessage(
                  { id: 'employees.courseListTruncated' },
                  { shown: courseItems.length, total: courses.data?.total ?? 0 },
                )}
              </p>
            )}

            {emptyFolder && (
              <p role="alert" className="text-sm text-danger">
                {intl.formatMessage({ id: 'groups.assignNoPublished' })}
              </p>
            )}
            {target?.kind === 'folder' && !emptyFolder && !folderPublished.isLoading && (
              <p className="text-xs text-text-muted">
                {intl.formatMessage({ id: 'employees.folderPublishedCount' }, { count: publishedInFolder })}
              </p>
            )}

            <Input
              label={intl.formatMessage({ id: 'employees.deadlineLabel' })}
              type="date"
              value={deadline}
              onChange={(event) => setDeadline(event.target.value)}
            />
          </div>

          {group.member_count === 0 && (
            <p className="mt-3 text-sm text-warning">{intl.formatMessage({ id: 'groups.assignEmptyGroup' })}</p>
          )}
          {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}

          <div className="mt-5 flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>{intl.formatMessage({ id: 'groups.cancel' })}</Button>
            <Button disabled={!target || emptyFolder || assign.isPending} onClick={submit}>
              {assign.isPending
                ? intl.formatMessage({ id: 'employees.assigning' })
                : intl.formatMessage({ id: 'groups.assignAction' })}
            </Button>
          </div>
        </>
      )}
    </Modal>
  )
}
