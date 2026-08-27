import { useRef, useState } from 'react'
import { useIntl } from 'react-intl'
import { useQueryClient } from '@tanstack/react-query'
import {
  useAssignCourseFolder,
  useFolderCourseEnrollments,
  type CourseFolder,
  type CourseFolderAssignmentResult,
} from '../../api/course-folders'
import { useCourses } from '../../api/courses'
import { useDeleteEnrollment } from '../../api/enrollments'
import { useUsers } from '../../api/users'
import { ApiError } from '../../api/client'
import type { EnrollmentRead } from '../../types'
import { Button, Input, Modal } from '../ui'
import { ShimmerSkeleton } from '../ui/ShimmerSkeleton'

type FolderAssignmentDialogProps = {
  folder: CourseFolder
  onClose: () => void
}

/** One enrollment this dialog is about to delete, with the words to report it by. */
type PendingRemoval = {
  enrollmentId: string
  personName: string
  courseTitle: string
}

/** What actually happened, in the dialog's own numbers rather than the server's. */
type Outcome = {
  assigned: CourseFolderAssignmentResult | null
  removed: number
  /** Enrollments that could not be deleted because the person had already started. */
  keptStarted: number
  failures: { personName: string; courseTitle: string; detail: string }[]
}

/**
 * The server deletes an enrollment only while it is still `assigned`.
 *
 * Mirrors `EnrollmentService.delete`, which answers 409 "Only assigned (not started)
 * enrollments can be removed" for anything else. Knowing the rule up front is what lets
 * the dialog say *why* a tick is locked instead of letting the admin discover it by
 * getting an error.
 */
function isRemovable(enrollment: EnrollmentRead): boolean {
  return enrollment.status === 'assigned'
}

/**
 * Manage who holds the courses of one folder.
 *
 * The tick is the answer to the only question the dialog exists for — does this person
 * have this folder? — and it is now also the control: ticking assigns the folder,
 * unticking takes it back.
 *
 * Two things it used to hide, both of which sent the admin away with the wrong idea of
 * what happened:
 *
 * 1. It never read the existing enrollments, so it could not say who already had the
 *    folder's courses — the answer only arrived afterwards as a `skipped_existing_count`.
 * 2. The server assigns PUBLISHED courses only. A folder of drafts answers 200 with
 *    `course_count: 0`, which the dialog reported as "0 enrollments across 0 courses"
 *    with no hint that the drafts were the reason. The published set is known before the
 *    button is pressed, so the warning belongs there.
 *
 * And one it used to do honestly but uselessly: a person who already held the whole
 * folder got a ticked *and disabled* checkbox, because the dialog could only grant. It
 * can now revoke, so the tick is live — with one boundary the server draws and the row
 * has to state in words (see `lockedReason`).
 *
 * **Half-started folders.** `DELETE /enrollments/{id}` refuses any enrollment that is
 * not still `assigned`, so someone who started *some* of the folder is only partly
 * revocable. Rather than block the whole row (which would strand the untouched courses)
 * or pretend the started ones went away, unticking removes every not-started enrollment
 * and the row says, before the click, how many started ones will stay behind. The tick
 * locks only when *nothing* is removable — at that point unticking could do nothing at
 * all, and a checkbox that moves without effect is the lie this dialog started out as.
 */
export function FolderAssignmentDialog({ folder, onClose }: FolderAssignmentDialogProps) {
  const intl = useIntl()
  const queryClient = useQueryClient()
  const users = useUsers({ role: 'employee', is_active: true })
  // The same set the server will act on: published courses of this folder.
  const publishedCourses = useCourses({ folderId: folder.id, status: 'published' })
  const assign = useAssignCourseFolder()
  const removeEnrollment = useDeleteEnrollment()
  // Only what the admin changed relative to the server's answer. The tick itself is
  // derived (`isTicked`), so a person who already holds the folder starts ticked without
  // this state having to be seeded from a query that may not have resolved yet.
  const [overrides, setOverrides] = useState<Record<string, boolean>>({})
  const [deadline, setDeadline] = useState('')
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const [errors, setErrors] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  // `assign.isPending` alone still lets two clicks in the same tick both fire, and the
  // flow is now several awaits long, which widens exactly that window.
  const submitted = useRef(false)
  const employees = users.data?.items ?? []
  const courses = publishedCourses.data?.items ?? []
  const publishedCount = publishedCourses.data?.total ?? courses.length
  // `course_count` counts every course in the folder, published or not.
  const unpublishedCount = Math.max(0, (folder.course_count ?? publishedCount) - publishedCount)
  const noPublished = publishedCourses.isSuccess && publishedCount === 0
  const { enrolledCountByUser, enrollmentsByUser } = useFolderCourseEnrollments(
    courses.map((course) => course.id),
  )

  function toggle(userId: string) {
    // Read the previous tick out of `current`, never out of `isTicked`: that closure holds
    // the `overrides` of the render that attached this handler. Two changes for the same
    // person batched into one commit — a double click on the row, or a click right after a
    // keyboard toggle — would both compute from the same pre-batch value, so the second
    // would be a no-op and the tick would disagree with what the admin just did.
    setOverrides((current) => ({ ...current, [userId]: !(current[userId] ?? hasAll(userId)) }))
  }

  /**
   * Someone who already holds every published course of this folder.
   *
   * The checkbox has to say so. It used to render from a `selected` list that starts
   * empty, so a person who already had the whole folder appeared UNTICKED — the one
   * question the admin opens this dialog to answer, answered wrongly.
   */
  function hasAll(userId: string): boolean {
    return publishedCount > 0 && (enrolledCountByUser[userId] ?? 0) >= publishedCount
  }

  function isTicked(userId: string): boolean {
    return overrides[userId] ?? hasAll(userId)
  }

  /** Their enrollments in this folder that the server would still let us delete. */
  function removableOf(userId: string): EnrollmentRead[] {
    return (enrollmentsByUser[userId] ?? []).filter(isRemovable)
  }

  /** Their enrollments in this folder that have already started, so they are stuck. */
  function startedCountOf(userId: string): number {
    return (enrollmentsByUser[userId] ?? []).filter((row) => !isRemovable(row)).length
  }

  /**
   * Why this person's tick cannot move, in words rather than a mute `disabled`.
   *
   * Null when it can move. Only the person who holds the folder and has started every
   * one of its courses is stuck: there is nothing left for unticking to delete.
   */
  function lockedReason(userId: string): string | null {
    if (!hasAll(userId)) return null
    if (removableOf(userId).length > 0) return null
    return intl.formatMessage(
      { id: 'content.assignFolderStartedLocked' },
      { count: startedCountOf(userId) },
    )
  }

  function alreadyHas(userId: string): string | null {
    const done = enrolledCountByUser[userId] ?? 0
    if (done === 0 || publishedCount === 0) return null
    if (done >= publishedCount) return intl.formatMessage({ id: 'content.assignFolderAlreadyAll' }, { count: publishedCount })
    return intl.formatMessage({ id: 'content.assignFolderAlreadySome' }, { done, total: publishedCount })
  }

  const toAssign = employees.filter((employee) => isTicked(employee.id) && !hasAll(employee.id))
  const toRemove = employees.filter(
    (employee) => !isTicked(employee.id) && hasAll(employee.id) && removableOf(employee.id).length > 0,
  )
  const removals: PendingRemoval[] = toRemove.flatMap((employee) =>
    removableOf(employee.id).map((enrollment) => ({
      enrollmentId: enrollment.id,
      personName: employee.full_name,
      courseTitle:
        courses.find((course) => course.id === enrollment.course_id)?.title ?? enrollment.course_title,
    })),
  )
  const keptStarted = toRemove.reduce((total, employee) => total + startedCountOf(employee.id), 0)

  function actionLabel(): string {
    if (toAssign.length > 0 && toRemove.length > 0) {
      return intl.formatMessage(
        { id: 'content.assignFolderActionBoth' },
        { assign: toAssign.length, remove: toRemove.length },
      )
    }
    if (toRemove.length > 0) {
      return intl.formatMessage({ id: 'content.assignFolderActionRemove' }, { count: toRemove.length })
    }
    if (toAssign.length > 0) {
      return intl.formatMessage({ id: 'content.assignFolderActionAssign' }, { count: toAssign.length })
    }
    return intl.formatMessage({ id: 'content.assignFolderAction' }, { count: publishedCount })
  }

  async function submit() {
    if (submitted.current) return
    // Deleting enrollments is not undoable from here, so it is never a side effect of a
    // button whose label the admin may not have read. Same `window.confirm` the rest of
    // this area uses (`Employees.tsx`, `CourseFolderSidebar.tsx`).
    if (
      removals.length > 0 &&
      !window.confirm(
        intl.formatMessage(
          { id: 'content.assignFolderRemoveConfirm' },
          { people: toRemove.length, count: removals.length, kept: keptStarted },
        ),
      )
    ) {
      return
    }
    submitted.current = true
    setBusy(true)
    setErrors([])

    // Each delete is reported on its own: a 409 here means the person started that course
    // between the list being fetched and the click, and the remaining ones are still
    // perfectly removable. Aborting the batch on the first failure would leave the folder
    // in a state nobody asked for.
    let removed = 0
    const failures: Outcome['failures'] = []
    for (const removal of removals) {
      try {
        await removeEnrollment.mutateAsync(removal.enrollmentId)
        removed += 1
      } catch (cause) {
        failures.push({
          personName: removal.personName,
          courseTitle: removal.courseTitle,
          detail:
            cause instanceof ApiError
              ? cause.body.detail
              : intl.formatMessage({ id: 'content.assignFolderRemoveFailedUnknown' }),
        })
      }
    }

    let assigned: CourseFolderAssignmentResult | null = null
    let assignError: string | null = null
    if (toAssign.length > 0) {
      try {
        assigned = await assign.mutateAsync({
          id: folder.id,
          userIds: toAssign.map((employee) => employee.id),
          deadline,
        })
      } catch (cause) {
        assignError =
          cause instanceof ApiError
            ? cause.body.detail
            : intl.formatMessage({ id: 'content.assignFolderError' })
      }
    }

    // The rows have to repaint from the server, not from the counts this pass computed:
    // `useFolderCourseEnrollments` caches per course under `['enrollments', 'by-course']`
    // and the talent screens count assigned training per person.
    await queryClient.invalidateQueries({ queryKey: ['enrollments'] })
    queryClient.invalidateQueries({ queryKey: ['talent'] })
    setBusy(false)

    const failureLines = failures.map((failure) =>
      intl.formatMessage(
        { id: 'content.assignFolderRemoveFailed' },
        { name: failure.personName, course: failure.courseTitle, detail: failure.detail },
      ),
    )
    if (assigned === null && removed === 0) {
      // Nothing landed. Say why — every reason, not just the first — and let the button
      // work again, instead of a result panel reporting a change that did not happen.
      submitted.current = false
      const lines = assignError ? [...failureLines, assignError] : failureLines
      setErrors(lines.length > 0 ? lines : [intl.formatMessage({ id: 'content.assignFolderError' })])
      return
    }
    setErrors(assignError ? [assignError] : [])
    setOutcome({ assigned, removed, keptStarted, failures })
  }

  return (
    <Modal open onClose={onClose} size="md">
      <h2 className="text-lg font-semibold text-text">{intl.formatMessage({ id: 'content.assignFolderTitle' }, { name: folder.name })}</h2>
      <p className="mt-1 text-sm text-text-secondary">{intl.formatMessage({ id: 'content.assignFolderDescription' })}</p>
      {outcome ? (
        <div className="mt-5">
          {outcome.assigned && <p className="text-sm text-text">{intl.formatMessage({ id: 'content.assignFolderSuccess' }, { enrollments: outcome.assigned.created_count, courses: outcome.assigned.course_count })}</p>}
          {outcome.assigned?.course_count === 0 && <p className="mt-1 text-sm text-warning">{intl.formatMessage({ id: 'content.assignFolderNoPublished' })}</p>}
          {(outcome.assigned?.skipped_existing_count ?? 0) > 0 && <p className="mt-1 text-sm text-text-muted">{intl.formatMessage({ id: 'content.assignFolderSkipped' }, { count: outcome.assigned?.skipped_existing_count })}</p>}
          {outcome.removed > 0 && <p className="mt-1 text-sm text-text">{intl.formatMessage({ id: 'content.assignFolderRemoved' }, { count: outcome.removed })}</p>}
          {outcome.keptStarted > 0 && <p className="mt-1 text-sm text-text-muted">{intl.formatMessage({ id: 'content.assignFolderRemoveKept' }, { count: outcome.keptStarted })}</p>}
          {outcome.failures.map((failure) => (
            <p key={`${failure.personName}:${failure.courseTitle}`} role="alert" className="mt-1 text-sm text-danger">
              {intl.formatMessage({ id: 'content.assignFolderRemoveFailed' }, { name: failure.personName, course: failure.courseTitle, detail: failure.detail })}
            </p>
          ))}
          {errors.map((line) => <p key={line} role="alert" className="mt-1 text-sm text-danger">{line}</p>)}
          <Button className="mt-5" onClick={onClose}>{intl.formatMessage({ id: 'content.assignFolderDone' })}</Button>
        </div>
      ) : (
        <>
          {noPublished && <p role="alert" className="mt-4 rounded-lg border border-warning/40 px-3 py-2 text-sm text-warning">{intl.formatMessage({ id: 'content.assignFolderNoPublished' })}</p>}
          {!noPublished && unpublishedCount > 0 && <p className="mt-4 text-xs text-text-muted">{intl.formatMessage({ id: 'content.assignFolderDraftsIgnored' }, { count: unpublishedCount })}</p>}
          <div className="mt-5 max-h-64 divide-y divide-border overflow-y-auto rounded-lg border border-border px-3">
            {users.isLoading ? <div className="space-y-3 py-4" aria-hidden="true"><ShimmerSkeleton className="h-10 w-full" /><ShimmerSkeleton className="h-10 w-full" /><ShimmerSkeleton className="h-10 w-full" /></div> : employees.map((employee) => {
              const enrolled = alreadyHas(employee.id)
              const locked = lockedReason(employee.id)
              const ticked = isTicked(employee.id)
              // How much of an untick this row would not manage. Said in both tick states
              // on purpose: before the click it warns, after it explains what stays.
              const stuck = hasAll(employee.id) && !locked ? startedCountOf(employee.id) : 0
              return (
                <label key={employee.id} className={`flex items-center gap-3 py-3 ${locked ? 'cursor-default' : 'cursor-pointer'}`}>
                  <input type="checkbox" checked={ticked} disabled={!!locked || busy} onChange={() => toggle(employee.id)} className="size-4 accent-primary disabled:opacity-60" />
                  <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium text-text">{employee.full_name}</span><span className="block truncate text-xs text-text-muted">{employee.email}</span></span>
                  {(enrolled || locked || stuck > 0) && (
                    <span className="shrink-0 text-right">
                      {enrolled && <span className="block text-xs text-accent">{enrolled}</span>}
                      {locked && <span className="block text-xs text-warning">{locked}</span>}
                      {!locked && stuck > 0 && <span className="block text-xs text-text-muted">{intl.formatMessage({ id: 'content.assignFolderStartedKept' }, { count: stuck })}</span>}
                    </span>
                  )}
                </label>
              )
            })}
            {!users.isLoading && employees.length === 0 && <p className="py-4 text-sm text-text-muted">{intl.formatMessage({ id: 'content.assignFolderNoPeople' })}</p>}
          </div>
          <Input className="mt-4" label={intl.formatMessage({ id: 'content.assignmentDeadline' })} type="date" value={deadline} onChange={(event) => setDeadline(event.target.value)} />
          {errors.map((line) => <p key={line} role="alert" className="mt-3 text-sm text-danger">{line}</p>)}
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>{intl.formatMessage({ id: 'content.folderCancel' })}</Button>
            <Button disabled={(toAssign.length === 0 && toRemove.length === 0) || busy || (noPublished && toRemove.length === 0)} onClick={submit}>{actionLabel()}</Button>
          </div>
        </>
      )}
    </Modal>
  )
}
