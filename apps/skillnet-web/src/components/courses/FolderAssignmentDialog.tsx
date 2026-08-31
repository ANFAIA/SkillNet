import { useDeferredValue, useId, useRef, useState } from 'react'
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
import { useUserGroups, type UserGroup } from '../../api/user-groups'
import { apiErrorMessage } from '../../lib/apiErrors'
import type { EnrollmentRead, User } from '../../types'
import { Button, Input, Modal, Pager, SearchField } from '../ui'
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

/**
 * One decision the admin made, frozen at the moment they made it.
 *
 * The enrollment facts behind a row — does this person hold the whole folder, which of
 * their enrollments is still deletable — are only known for the page on screen. So a
 * tick has to be *resolved into an action when it is clicked*, not re-derived at submit
 * time from data that has since paged away. Storing the intent instead of the tick is
 * what lets somebody be ticked on page 1, unticked on page 3, and still have both
 * decisions honoured by one button.
 */
type Staged =
  | { kind: 'assign'; person: User }
  | { kind: 'remove'; person: User; removals: PendingRemoval[]; keptStarted: number }

/** What actually happened, in the dialog's own numbers rather than the server's. */
type Outcome = {
  assigned: CourseFolderAssignmentResult | null
  removed: number
  /** Enrollments that could not be deleted because the person had already started. */
  keptStarted: number
  failures: { personName: string; courseTitle: string; detail: string }[]
}

/**
 * Groups shown at a time in this dialog.
 *
 * Smaller than the people page because the section sits above it and must not push the
 * list of people off the screen — the two are read together, not one after the other.
 */
const GROUP_PAGE_SIZE = 8

/** The most rows the enrollment read may need. Mirrors the endpoint's own cap. */
const ENROLLMENT_PAGE_CAP = 100
/** Never fewer than this many people per page, however many courses the folder holds. */
const MIN_PAGE_SIZE = 5
const MAX_PAGE_SIZE = 25

/**
 * How many people fit on one page without the enrollment read truncating.
 *
 * The tick state of a row is "does this person hold all of the folder's published
 * courses", which needs one enrollment row per (person, course) pair. The endpoint
 * returns at most 100 rows, so the page size is not a taste decision — it is
 * `100 / courses`. A folder of 2 courses shows 25 people; one of 20 shows 5.
 *
 * **The floor wins past 20 courses, and then the bound does not hold.** Five people is
 * already the fewest a list can show and still be a list, so a folder of 30 courses asks
 * for 150 rows and gets 100. That is why `useFolderCourseEnrollments` reports `truncated`
 * and the dialog says so out loud: the arithmetic makes truncation impossible in the
 * ordinary case, not in every case, and the warning covers the rest. Nothing is destroyed
 * either way — an incomplete read makes `hasAll` false, and a row that is not `hasAll`
 * cannot be staged as a removal.
 */
function pageSizeFor(publishedCount: number): number {
  if (publishedCount <= 0) return MAX_PAGE_SIZE
  const fits = Math.floor(ENROLLMENT_PAGE_CAP / publishedCount)
  return Math.max(MIN_PAGE_SIZE, Math.min(MAX_PAGE_SIZE, fits))
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
 * have this folder? — and it is also the control: ticking assigns the folder, unticking
 * takes it back.
 *
 * **The list is a page, and it says so.** It used to render whatever `GET /users`
 * returned by default: the first fifty employees, with nothing on screen to suggest a
 * fifty-first existed. In a company of sixty, ten people simply could not be assigned
 * anything from here and the screen looked complete. There is now a search box, a page
 * at a time, and a line that says "1-25 de 240" whether or not it overflows — the count
 * is what tells the admin the list is a window in the first place.
 *
 * **Groups come first, in the same row shape, and the section header carries the
 * difference.** A person's checkbox is a *state* with two directions: ticked means "has
 * the folder", unticking revokes. A group's can only ever be an *action* — the dialog
 * holds one page of people, so it cannot know whether every member of a group already
 * has the folder, and a box that claimed to know would be exactly the lie the rest of
 * this dialog exists to undo.
 *
 * That distinction used to be carried by the control's *shape* (groups were pill
 * buttons under the people list), which cost the admin the obvious reading — "assign
 * this to a group" is the common case and it was the least visible thing in the dialog.
 * The shape is now the same for both, so the meaning is carried by the two places that
 * cost no screen space and are more precise than a paragraph would be: the section
 * heading names what its boxes are about ("Grupos · a quién asignársela" against
 * "Personas · quién la tiene"), and each box is *labelled by what that row does* —
 * "Asignar la carpeta a todo el grupo Turno de tarde" against "Ana tiene esta carpeta",
 * a proposition whose truth value is the tick. The row's own detail (members, email,
 * how much of the folder they hold) stays reachable as the box's `aria-describedby`.
 * A group tick stages "assign to everyone in here" and never revokes; the membership is
 * still resolved by the server, and the tick is only undoable in the sense that any
 * un-submitted intent is.
 *
 * The two help paragraphs that used to state all this are gone. A paragraph explaining
 * what a checkbox does is an admission that the checkbox does not explain itself, and
 * it was also the vaguer of the two answers: it spoke for a whole section where the
 * label speaks for the row under the cursor.
 *
 * Two other things it says out loud, both of which used to be discovered afterwards:
 * who already holds the folder's courses (rather than a `skipped_existing_count` after
 * the fact), and that only **published** courses are ever assigned, so a folder of
 * drafts enrols nobody.
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
  // Prefix for the per-row ids. Each box is named after what its own row does and
  // described by that row's own detail, so nothing a section-wide paragraph used to say
  // has to be said at all.
  const rowId = useId()
  // The same set the server will act on: published courses of this folder.
  const publishedCourses = useCourses({ folderId: folder.id, status: 'published' })
  const [groupSearch, setGroupSearch] = useState('')
  const [groupOffset, setGroupOffset] = useState(0)
  const deferredGroupSearch = useDeferredValue(groupSearch.trim())
  const groupsQuery = useUserGroups({
    search: deferredGroupSearch || undefined,
    offset: groupOffset,
    limit: GROUP_PAGE_SIZE,
  })
  // Whether the organization has *any* group, asked separately and never filtered. The
  // page's own `total` drops to zero on a search that matches nothing, and keying the
  // section off that made the whole block — search box included — disappear the moment a
  // typo stopped matching, with no way left to correct it.
  const anyGroups = useUserGroups({ limit: 1 })
  const assign = useAssignCourseFolder()
  const removeEnrollment = useDeleteEnrollment()
  // Only what the admin changed relative to the server's answer, keyed by user id and
  // kept across pages. The tick of an untouched row is *derived* (`isTicked`), so a
  // person who already holds the folder starts ticked without this state having to be
  // seeded from a query that may not have resolved yet.
  const [staged, setStaged] = useState<Record<string, Staged>>({})
  // The chosen groups themselves, not their ids: `member_count` has to survive paging
  // and searching. Summing it out of the *page* made a group picked on page 1 contribute
  // zero from page 2, so "hasta N personas" quietly shrank as the admin moved around —
  // the same lesson the people ticks already learned, one list over.
  const [pickedGroups, setPickedGroups] = useState<Record<string, UserGroup>>({})
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const [deadline, setDeadline] = useState('')
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const [errors, setErrors] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  // `assign.isPending` alone still lets two clicks in the same tick both fire, and the
  // flow is several awaits long, which widens exactly that window.
  const submitted = useRef(false)

  const courses = publishedCourses.data?.items ?? []
  const publishedCount = publishedCourses.data?.total ?? courses.length
  // `course_count` counts every course in the folder, published or not.
  const unpublishedCount = Math.max(0, (folder.course_count ?? publishedCount) - publishedCount)
  const noPublished = publishedCourses.isSuccess && publishedCount === 0

  const pageSize = pageSizeFor(publishedCount)
  const deferredSearch = useDeferredValue(search.trim())
  const users = useUsers({
    role: 'employee',
    is_active: true,
    search: deferredSearch || undefined,
    offset,
    limit: pageSize,
  })
  const employees = users.data?.items ?? []
  const total = users.data?.total ?? 0

  const { enrolledCountByUser, enrollmentsByUser, truncated } = useFolderCourseEnrollments(
    folder.id,
    employees.map((employee) => employee.id),
  )

  /**
   * Turn one click into the action it means, using the facts currently on screen.
   *
   * Resolved here rather than at submit time because `hasAll` and `removableOf` only
   * answer for the visible page — by the time the admin presses the button from page 3,
   * page 1's rows are gone and re-deriving their intent would be guesswork.
   */
  function toggle(employee: User) {
    setStaged((current) => {
      // Read the previous state out of `current`, never out of `isTicked`: that closure
      // holds the `staged` of the render that attached this handler. Two changes for the
      // same person batched into one commit — a double click, or a click right after a
      // keyboard toggle — would both compute from the same pre-batch value, so the second
      // would be a no-op and the tick would disagree with what the admin just did.
      const existing = current[employee.id]
      const ticked = existing ? existing.kind === 'assign' : hasAll(employee.id)
      const next = { ...current }
      // Back to what the server says: drop the entry instead of storing "no change",
      // so the button's counts never include a decision that undid itself.
      if (ticked === hasAll(employee.id)) {
        next[employee.id] = ticked
          ? {
              kind: 'remove',
              person: employee,
              removals: removableOf(employee.id).map((enrollment) => ({
                enrollmentId: enrollment.id,
                personName: employee.full_name,
                courseTitle:
                  courses.find((course) => course.id === enrollment.course_id)?.title ??
                  enrollment.course_title,
              })),
              keptStarted: startedCountOf(employee.id),
            }
          : { kind: 'assign', person: employee }
        return next
      }
      delete next[employee.id]
      return next
    })
  }

  function changeSearch(value: string) {
    setSearch(value)
    // Page 4 of the old result set means nothing for the new one, and staying there is
    // how a search with plenty of matches comes back empty.
    setOffset(0)
  }

  /**
   * Someone who already holds every published course of this folder.
   *
   * Only meaningful for a person on the current page: the enrollment read is scoped to
   * it. For anybody else this answers `false`, which is why `toAssign`/`toRemove` only
   * consider people whose tick the admin actually moved.
   */
  function hasAll(userId: string): boolean {
    return publishedCount > 0 && (enrolledCountByUser[userId] ?? 0) >= publishedCount
  }

  function isTicked(userId: string): boolean {
    const entry = staged[userId]
    return entry ? entry.kind === 'assign' : hasAll(userId)
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

  // Every decision the admin has made in this dialog, on whatever page they made it.
  const decisions = Object.values(staged)
  const toAssign = decisions.filter((entry) => entry.kind === 'assign').map((entry) => entry.person)
  const removeDecisions = decisions.filter(
    (entry): entry is Extract<Staged, { kind: 'remove' }> => entry.kind === 'remove',
  )
  const toRemove = removeDecisions.map((entry) => entry.person)
  const removals: PendingRemoval[] = removeDecisions.flatMap((entry) => entry.removals)
  const keptStarted = removeDecisions.reduce((sum, entry) => sum + entry.keptStarted, 0)
  // Decisions whose row is not on this page. Said out loud, because a button that reads
  // "assign to 4 people" next to a page showing one tick is otherwise alarming.
  const visible = new Set(employees.map((employee) => employee.id))
  const offPage = decisions.filter((entry) => !visible.has(entry.person.id)).length
  const groups = groupsQuery.data?.items ?? []
  const groupTotal = groupsQuery.data?.total ?? 0
  const pickedGroupList = Object.values(pickedGroups)
  const pickedGroupIds = Object.keys(pickedGroups)
  const groupPeople = pickedGroupList.reduce((sum, group) => sum + group.member_count, 0)
  // Groups chosen on a page that is no longer on screen. Same reason as `offPage` for
  // people: a button announcing three groups next to a list showing one is alarming.
  const groupsOffPage = pickedGroupList.filter(
    (picked) => !groups.some((group) => group.id === picked.id),
  ).length
  const nothingToDo = toAssign.length === 0 && toRemove.length === 0 && pickedGroupIds.length === 0

  function toggleGroup(group: UserGroup) {
    setPickedGroups((current) => {
      const next = { ...current }
      if (next[group.id]) delete next[group.id]
      // Store the row the admin actually saw. A later page or a rename cannot retro-fit
      // a count onto a decision that was made against the old one.
      else next[group.id] = group
      return next
    })
  }

  function changeGroupSearch(value: string) {
    setGroupSearch(value)
    // Page 2 of the old result set means nothing for the new one.
    setGroupOffset(0)
  }

  function actionLabel(): string {
    if (pickedGroupIds.length > 0 && toRemove.length === 0) {
      // "Asignar a 0 personas y 1 grupo" is what the combined wording produces when
      // nobody is ticked individually, and a button that opens by announcing a zero
      // reads like a bug. Only name the half that exists.
      return toAssign.length === 0
        ? intl.formatMessage(
            { id: 'content.assignFolderActionGroupsOnly' },
            { groups: pickedGroupIds.length },
          )
        : intl.formatMessage(
            { id: 'content.assignFolderActionWithGroups' },
            { people: toAssign.length, groups: pickedGroupIds.length },
          )
    }
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
          detail: apiErrorMessage(intl, cause, 'content.assignFolderRemoveFailedUnknown'),
        })
      }
    }

    let assigned: CourseFolderAssignmentResult | null = null
    let assignError: string | null = null
    if (toAssign.length > 0 || pickedGroupIds.length > 0) {
      try {
        // People and groups go in one request: the server unions them, deduplicates, and
        // reports one set of counts. Two requests would double-count anybody who is both.
        assigned = await assign.mutateAsync({
          id: folder.id,
          userIds: toAssign.map((employee) => employee.id),
          groupIds: pickedGroupIds,
          deadline,
        })
      } catch (cause) {
        assignError = apiErrorMessage(intl, cause, 'content.assignFolderError')
      }
    }

    // The rows have to repaint from the server, not from the counts this pass computed:
    // `useFolderCourseEnrollments` caches under `['enrollments', 'by-folder']` and the
    // talent screens count assigned training per person.
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
    setStaged({})
    setPickedGroups({})
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
          {(outcome.assigned?.skipped_inactive_count ?? 0) > 0 && <p className="mt-1 text-sm text-text-muted">{intl.formatMessage({ id: 'groups.assignSkippedInactive' }, { count: outcome.assigned?.skipped_inactive_count })}</p>}
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

          {(anyGroups.data?.total ?? 0) > 0 && (
            <section className="mt-5">
              {/* The row shape is the same as a person's, so the heading is where the
                  difference gets said in the fewest words. See the component docstring. */}
              <h3 className="text-sm font-medium text-text">
                {intl.formatMessage({ id: 'content.assignFolderGroups' })}
                <span className="font-normal text-text-secondary"> · {intl.formatMessage({ id: 'content.assignFolderGroupsScope' })}</span>
              </h3>
              {/* The search box appears only once the rail has more groups than a page.
                  Below that it is a control with nothing to do, taking the room the list
                  itself needs — this section sits above the people and cannot grow. */}
              {(anyGroups.data?.total ?? 0) > GROUP_PAGE_SIZE && (
                <div className="mt-2">
                  <SearchField
                    label={intl.formatMessage({ id: 'content.assignFolderSearchGroups' })}
                    placeholder={intl.formatMessage({ id: 'content.assignFolderSearchGroups' })}
                    value={groupSearch}
                    onChange={(event) => changeGroupSearch(event.target.value)}
                  />
                </div>
              )}
              <div className="mt-2 max-h-48 divide-y divide-border overflow-y-auto rounded-lg border border-border px-3">
                {groupsQuery.isLoading ? (
                  <div className="space-y-3 py-4" aria-hidden="true"><ShimmerSkeleton className="h-10 w-full" /><ShimmerSkeleton className="h-10 w-full" /></div>
                ) : groups.length === 0 ? (
                  <p className="py-4 text-sm text-text-muted">{intl.formatMessage({ id: 'content.assignFolderNoGroups' })}</p>
                ) : groups.map((group) => {
                  const picked = !!pickedGroups[group.id]
                  const membersId = `${rowId}-g-${group.id}`
                  return (
                    <label key={group.id} className="flex cursor-pointer items-center gap-3 py-3">
                      {/* Named after the action, never after a state: the dialog holds one
                          page of people and cannot know what a whole group already has. */}
                      <input type="checkbox" checked={picked} disabled={busy} onChange={() => toggleGroup(group)} aria-label={intl.formatMessage({ id: 'content.assignFolderGroupBox' }, { name: group.name })} aria-describedby={membersId} className="size-4 accent-primary disabled:opacity-60" />
                      <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium text-text">{group.name}</span><span id={membersId} className="block truncate text-xs text-text-muted">{intl.formatMessage({ id: 'groups.personMemberCount' }, { count: group.member_count })}</span></span>
                      {picked && <span className="shrink-0 text-xs text-accent">{intl.formatMessage({ id: 'content.assignFolderGroupStaged' })}</span>}
                    </label>
                  )
                })}
              </div>
              {(anyGroups.data?.total ?? 0) > GROUP_PAGE_SIZE && (
                <Pager
                  className="mt-2"
                  offset={groupOffset}
                  shown={groups.length}
                  total={groupTotal}
                  pageSize={GROUP_PAGE_SIZE}
                  disabled={busy || groupsQuery.isFetching}
                  onChange={setGroupOffset}
                />
              )}
              {pickedGroupIds.length > 0 && (
                <p className="mt-2 text-xs text-text-secondary">
                  {intl.formatMessage({ id: 'content.assignFolderGroupsPicked' }, { groups: pickedGroupIds.length, people: groupPeople })}
                  {groupsOffPage > 0 && ' ' + intl.formatMessage({ id: 'content.assignFolderGroupsOffPage' }, { count: groupsOffPage })}
                </p>
              )}
            </section>
          )}

          <section className="mt-5">
            <h3 className="text-sm font-medium text-text">
              {intl.formatMessage({ id: 'content.assignFolderPeople' })}
              <span className="font-normal text-text-secondary"> · {intl.formatMessage({ id: 'content.assignFolderPeopleScope' })}</span>
            </h3>

            <div className="mt-3">
              <SearchField
                label={intl.formatMessage({ id: 'content.assignFolderSearchPeople' })}
                placeholder={intl.formatMessage({ id: 'content.assignFolderSearchPeople' })}
                value={search}
                onChange={(event) => changeSearch(event.target.value)}
              />
            </div>

            <div className="mt-3 max-h-64 divide-y divide-border overflow-y-auto rounded-lg border border-border px-3">
              {users.isLoading ? <div className="space-y-3 py-4" aria-hidden="true"><ShimmerSkeleton className="h-10 w-full" /><ShimmerSkeleton className="h-10 w-full" /><ShimmerSkeleton className="h-10 w-full" /></div> : employees.map((employee) => {
                const enrolled = alreadyHas(employee.id)
                const locked = lockedReason(employee.id)
                const ticked = isTicked(employee.id)
                // How much of an untick this row would not manage. Said in both tick states
                // on purpose: before the click it warns, after it explains what stays.
                const stuck = hasAll(employee.id) && !locked ? startedCountOf(employee.id) : 0
                const emailId = `${rowId}-p-${employee.id}`
                const statusId = `${rowId}-s-${employee.id}`
                const hasStatus = Boolean(enrolled || locked || stuck > 0)
                return (
                  <label key={employee.id} className={`flex items-center gap-3 py-3 ${locked ? 'cursor-default' : 'cursor-pointer'}`}>
                    {/* Named after the state, because for a person there is one to read:
                        the label is the claim and the tick is its truth value. */}
                    <input type="checkbox" checked={ticked} disabled={!!locked || busy} onChange={() => toggle(employee)} aria-label={intl.formatMessage({ id: 'content.assignFolderPersonBox' }, { name: employee.full_name })} aria-describedby={hasStatus ? `${emailId} ${statusId}` : emailId} className="size-4 accent-primary disabled:opacity-60" />
                    <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium text-text">{employee.full_name}</span><span id={emailId} className="block truncate text-xs text-text-muted">{employee.email}</span></span>
                    {hasStatus && (
                      <span id={statusId} className="shrink-0 text-right">
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

            <Pager
              className="mt-2"
              offset={offset}
              shown={employees.length}
              total={total}
              pageSize={pageSize}
              disabled={busy || users.isFetching}
              onChange={setOffset}
            />
            {offPage > 0 && (
              <p className="mt-2 text-xs text-text-secondary">
                {intl.formatMessage({ id: 'content.assignFolderOffPage' }, { count: offPage })}
              </p>
            )}
            {truncated && (
              <p role="alert" className="mt-2 text-xs text-warning">
                {intl.formatMessage({ id: 'content.assignFolderTicksIncomplete' })}
              </p>
            )}
          </section>

          <Input className="mt-4" label={intl.formatMessage({ id: 'content.assignmentDeadline' })} type="date" value={deadline} onChange={(event) => setDeadline(event.target.value)} />
          {errors.map((line) => <p key={line} role="alert" className="mt-3 text-sm text-danger">{line}</p>)}
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>{intl.formatMessage({ id: 'content.folderCancel' })}</Button>
            <Button disabled={nothingToDo || busy || (noPublished && toRemove.length === 0)} onClick={submit}>{actionLabel()}</Button>
          </div>
        </>
      )}
    </Modal>
  )
}
