/**
 * The course library.
 *
 * Every name the user reads on this screen is "Biblioteca" / "Library". The route
 * (`/admin/contenido`), this file name and the `content.*` message namespace keep the
 * screen's old name on purpose: renaming them is a routing-and-namespace refactor that
 * touches bookmarks, the onboarding tour and every screen that links back here, and it
 * buys the user nothing. Only the visible strings were unified.
 */
import { useDeferredValue, useState } from 'react'
import { useIntl } from 'react-intl'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Badge, Button, Card, EmptyState, PageHeader, SearchField, Select } from '../../components/ui'
import { ShimmerSkeleton } from '../../components/ui/ShimmerSkeleton'
import { CourseFolderSidebar, type FolderFilter } from '../../components/courses/CourseFolderSidebar'
import { CourseFolderPicker } from '../../components/courses/CourseFolderPicker'
import { FolderAssignmentDialog } from '../../components/courses/FolderAssignmentDialog'
import { useCourseDeletion } from '../../components/courses/useCourseDeletion'
import { useCourseFolders, type CourseFolder } from '../../api/course-folders'
import { useArchiveCourse, useCourses, usePublishCourse, useUnarchiveCourse, useUpdateCourse } from '../../api/courses'
import { ApiError, post } from '../../api/client'
import { apiErrorMessage } from '../../lib/apiErrors'
import { startCourseFinalization } from '../../api/schema'
import { useAuth } from '../../hooks/useAuth'
import { canDeleteCourse } from '../../lib/canDeleteCourse'
import { staggerContainer, staggerItem } from '../../lib/motion'
import type { CourseRead, CourseStatus } from '../../types'

/**
 * The library's status filter.
 *
 * `failed` is not a `courses.status` value — a course whose creation died is still a
 * draft. It is a `generation_state` (migration 0025), and it earns a slot here because
 * "the wizard died half-way through making this" was, until that column existed,
 * indistinguishable from a draft somebody saved on purpose. That is what left the
 * tester with an unexplained dead row.
 */
const STATUSES = ['all', 'published', 'draft', 'archived', 'failed'] as const
type StatusFilter = (typeof STATUSES)[number]

/**
 * `archived` is still one of them, and it is no longer in the dropdown.
 *
 * Archiving now takes a course out of the library the way archiving a chat takes it out
 * of the chat list: the normal view does not show archived courses at all, and the way in
 * is one entry carrying their count. Leaving `archived` in the status dropdown as well
 * would be a second door to the same room — and the one that quietly contradicts what the
 * first one promises. The URL is unchanged (`?status=archived`), so old links still land
 * in the archive.
 */
const ARCHIVED: StatusFilter = 'archived'


function useStatusConfig() {
  const intl = useIntl()
  // `archived` used to share `primary` with the brand highlight, which made a course out
  // of circulation read as loudly as a published one. `danger` is the only variant Badge
  // offers that reads as a terminal state — there is no neutral/muted variant to use.
  const config: Record<string, { label: string; variant: 'accent' | 'warning' | 'primary' | 'danger' }> = {
    published: { label: intl.formatMessage({ id: 'status.published' }), variant: 'accent' },
    draft: { label: intl.formatMessage({ id: 'status.draft' }), variant: 'warning' },
    archived: { label: intl.formatMessage({ id: 'status.archived' }), variant: 'danger' },
  }
  return (status: CourseStatus) => config[status] ?? { label: status, variant: 'primary' as const }
}

function BookIcon() {
  return <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></svg>
}

function FolderTagIcon() {
  return <svg aria-hidden="true" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0"><path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" /></svg>
}

function PlusIcon() {
  return <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
}

/** A lidded box: the archive, here and on the entry that leads to it. */
function ArchiveBoxIcon({ size = 15 }: { size?: number }) {
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="20" height="5" rx="1" /><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8" /><path d="M10 12h4" /></svg>
}

/**
 * The way back out of the archive: the same box, with an arrow leaving through the lid.
 *
 * Deliberately the same body as `ArchiveBoxIcon` — they are one slot in two states, and
 * two unrelated drawings would make the row look like it changed shape. The arrow is what
 * tells them apart, and it points out of the box, so the difference reads without hovering
 * and without the label.
 */
function ArchiveRestoreIcon({ size = 15 }: { size?: number }) {
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="20" height="5" rx="1" /><path d="M4 8v11a2 2 0 0 0 2 2h4" /><path d="M20 8v3" /><path d="M16 18h6" /><path d="m19 15-3 3 3 3" /></svg>
}

/** Same drawing as `CourseFolderSidebar`'s, so delete looks like delete everywhere. */
function TrashIcon() {
  return <svg aria-hidden="true" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7" /></svg>
}

/** The gear the rest of the app uses for "settings of this thing". */
function SettingsIcon() {
  return <svg aria-hidden="true" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6h.09A1.65 1.65 0 0 0 10 3.09V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9v.09a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" /></svg>
}

function ChevronRightIcon() {
  return <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 18 6-6-6-6" /></svg>
}

function ChevronLeftIcon() {
  return <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6" /></svg>
}

/**
 * A row action reduced to its icon.
 *
 * Archive and delete are the two destructive actions on a row, and as words they sat in a
 * line of five or six buttons with the same weight as "View course". As icons they are
 * quieter and quicker to find — but an icon has no accessible name of its own, so
 * `label` is required and carries the course title: a screen reader in a list of twenty
 * rows needs to know *which* course this trash can belongs to.
 */
function IconAction({ label, onClick, disabled, danger = false, children }: {
  label: string
  onClick: () => void
  disabled?: boolean
  danger?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      aria-busy={disabled || undefined}
      className={`inline-flex h-8 w-8 items-center justify-center rounded-lg text-text-muted transition-colors cursor-pointer hover:bg-bg-muted disabled:opacity-50 disabled:cursor-not-allowed ${danger ? 'hover:text-danger' : 'hover:text-text'}`}
    >
      {children}
    </button>
  )
}

function LibrarySkeleton() {
  return (
    <div className="space-y-2" aria-hidden="true">
      {[0, 1, 2].map((item) => (
        <div key={item} className="border border-border rounded-lg p-5 flex items-center gap-4">
          <ShimmerSkeleton className="w-4 h-4" />
          <div className="flex-1 space-y-2"><ShimmerSkeleton className="h-4 w-2/5" /><ShimmerSkeleton className="h-3 w-3/5" /></div>
          <ShimmerSkeleton className="h-8 w-28" />
        </div>
      ))}
    </div>
  )
}

function canPublish(course: CourseRead): boolean {
  if (course.status !== 'draft') return false
  if (course.delivery_mode === 'dynamic') return (course.node_count ?? 0) > 0
  return (course.module_count ?? 0) > 0
}

function CourseRow({ course, folders, onMove, moving, onOpen, onPublish, onArchive, onUnarchive, onDelete, onRetry, publishing, archiving, unarchiving, deleting, retrying, error }: {
  course: CourseRead
  folders: { id: string; name: string }[]
  onMove: (course: CourseRead, folderId: string | null) => void
  moving: boolean
  onOpen: (path: string) => void
  onPublish: (course: CourseRead) => void
  onArchive: (course: CourseRead) => void
  onUnarchive: (course: CourseRead) => void
  onDelete: (course: CourseRead) => void
  onRetry: (course: CourseRead) => void
  publishing: boolean
  archiving: boolean
  unarchiving: boolean
  deleting: boolean
  retrying: boolean
  /**
   * What went wrong with this row's last action, if anything.
   *
   * On the row and not only at the top of the screen. Every action here is a small
   * control at the end of a line, and in a library of thirty courses the top of the list
   * is off-screen by the time the admin reaches row twenty — so a failed unarchive
   * produced no visible change anywhere they were looking, and the natural reading of
   * that is "the click didn't register". Hence the second press. Now the answer appears
   * where the question was asked, which matters more since the actions became icons: an
   * icon that quietly does nothing is even less legible than a button that does.
   */
  error?: string | null
}) {
  const intl = useIntl()
  const status = useStatusConfig()(course.status)
  const { user: currentUser } = useAuth()
  // A course whose creation run died is still `status: 'draft'`, so the plain status
  // badge says "borrador" and tells the admin nothing about why it has no content.
  const generationFailed = course.generation_state === 'failed'
  const generating = course.generation_state === 'in_progress'

  return (
    <Card variants={staggerItem}>
      <div className="flex min-w-0 flex-col gap-4 xl:flex-row xl:items-center">
        <div className="flex items-start gap-4 min-w-0 flex-1">
          <div className="text-text-muted shrink-0 mt-0.5"><BookIcon /></div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-sm font-medium text-text truncate min-w-0">{course.title}</span>
              <Badge variant={status.variant} badgeStyle="plain" className="shrink-0">{status.label}</Badge>
              {generationFailed && <Badge variant="danger" badgeStyle="plain" className="shrink-0">{intl.formatMessage({ id: 'content.generationFailed' })}</Badge>}
              {generating && <Badge variant="primary" badgeStyle="plain" className="shrink-0">{intl.formatMessage({ id: 'content.generationInProgress' })}</Badge>}
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1 text-xs text-text-muted">
              {course.delivery_mode === 'dynamic' ? (
                <><span className="text-primary font-medium">{intl.formatMessage({ id: 'content.dynamic' })}</span>{(course.node_count ?? 0) > 0 && <span>{intl.formatMessage({ id: 'content.nodesCount' }, { count: course.node_count })}</span>}</>
              ) : <span>{intl.formatMessage({ id: 'content.modulesCount' }, { count: course.module_count })}</span>}
              {/* A course is in zero or one folder. Saying which one — and saying so when
                  the answer is "none" — is the whole point: an empty gap here is what made
                  the admin open the picker to find out where the course already was. */}
              <span className={`inline-flex items-center gap-1 ${course.folder_name ? 'text-text-secondary' : 'italic'}`}>
                <FolderTagIcon />
                {course.folder_name
                  ? intl.formatMessage({ id: 'content.folderLabel' }, { name: course.folder_name })
                  : intl.formatMessage({ id: 'content.folderNone' })}
              </span>
              {course.outcome && <span className="truncate max-w-xs">{course.outcome}</span>}
              <span>{intl.formatMessage({ id: 'content.updatedAt' }, { date: new Date(course.updated_at ?? course.created_at).toLocaleDateString() })}</span>
            </div>
            {generationFailed && (
              <p className="mt-2 text-xs text-danger">
                {intl.formatMessage({ id: 'content.generationFailedDesc' })}
                {course.generation_error && <span className="text-text-secondary"> {course.generation_error}</span>}
              </p>
            )}
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-1 xl:justify-end">
          <CourseFolderPicker courseTitle={course.title} folderId={course.folder_id} folderName={course.folder_name} folders={folders} disabled={moving} onMove={(folderId) => onMove(course, folderId)} />
          {generationFailed && <Button variant="primary" size="sm" onClick={() => onRetry(course)} disabled={retrying}>{retrying ? intl.formatMessage({ id: 'content.retryingCreation' }) : intl.formatMessage({ id: 'content.retryCreation' })}</Button>}
          {generating && <Button variant="ghost" size="sm" onClick={() => onOpen(`/admin/crear-curso?course=${course.id}`)}>{intl.formatMessage({ id: 'content.resumeCreation' })}</Button>}
          {course.is_demo && <Button variant="primary" size="sm" data-tour="content-demo-open" onClick={() => onOpen('/admin/demo')}>{intl.formatMessage({ id: 'content.viewDemo' })}</Button>}
          {course.delivery_mode === 'dynamic' && !course.is_demo && <Button variant="ghost" size="sm" onClick={async () => { if (!currentUser) return; await post('/enrollments', { user_ids: [currentUser.id], course_id: course.id }).catch(() => {}); onOpen(`/admin/probar-curso/${course.id}`) }}>{intl.formatMessage({ id: 'content.test' })}</Button>}
          {course.module_count > 0 && course.delivery_mode !== 'dynamic' && <Button variant="ghost" size="sm" onClick={() => onOpen(`/admin/curso/${course.id}`)}>{intl.formatMessage({ id: 'content.viewCourse' })}</Button>}
          {canPublish(course) && <Button variant="ghost" size="sm" onClick={() => onPublish(course)} disabled={publishing}>{publishing ? intl.formatMessage({ id: 'preview.publishing' }) : intl.formatMessage({ id: 'preview.publish' })}</Button>}
          {/* The icon group: settings, the archive slot, delete — in that order, always,
              kept apart from the words by a margin alone. Three fixed places, because
              archive and unarchive are one slot in two states: the row does not shift
              under the pointer when a course is published or archived, which is exactly
              what the text buttons did as they came and went. The trash is last because
              it is the one that ends things. */}
          <div className="ml-1 flex items-center gap-0.5 sm:ml-3">
            <IconAction label={intl.formatMessage({ id: 'content.courseSettingsLabel' }, { title: course.title })} onClick={() => onOpen(`/admin/curso/${course.id}/ajustes`)}>
              <SettingsIcon />
            </IconAction>
            {/* One slot, and the accessible name is the action it currently performs —
                never a generic "archive toggle", which would tell a screen reader the
                shape of the code instead of what the press will do. */}
            {course.status === 'published' && (
              <IconAction label={intl.formatMessage({ id: 'content.courseArchiveLabel' }, { title: course.title })} onClick={() => onArchive(course)} disabled={archiving}>
                <ArchiveBoxIcon />
              </IconAction>
            )}
            {course.status === 'archived' && (
              <IconAction label={intl.formatMessage({ id: 'content.courseUnarchiveLabel' }, { title: course.title })} onClick={() => onUnarchive(course)} disabled={unarchiving}>
                <ArchiveRestoreIcon />
              </IconAction>
            )}
            {canDeleteCourse(course) && (
              <IconAction label={intl.formatMessage({ id: 'content.courseDeleteLabel' }, { title: course.title })} onClick={() => onDelete(course)} disabled={deleting} danger>
                <TrashIcon />
              </IconAction>
            )}
          </div>
        </div>
      </div>
      {error && <p role="alert" className="mt-3 border-t border-border pt-3 text-sm text-danger">{error}</p>}
    </Card>
  )
}

/**
 * What to say when publishing is refused — including when it was refused underneath.
 *
 * `CourseService.publish` answers 422 in English ("An outcome is required to publish"),
 * and showing that raw was wrong twice over. It is not in the admin's language, and after
 * a press of *Desarchivar* it names an action they never took: unarchiving republishes,
 * which is right and documented, but nobody outside the code knows it. So the sentence
 * starts from the button that was actually pressed, and `body.field` — which the error
 * envelope already carries — tells the three reasons apart without parsing English.
 *
 * `Employees.tsx` translates the 409 of removing a started course the same way, for the
 * same reason.
 */
function usePublishRefusal() {
  const intl = useIntl()
  return (reason: unknown, action: 'publish' | 'unarchive'): string => {
    const generic = action === 'publish' ? 'content.publishError' : 'content.unarchiveError'
    if (!(reason instanceof ApiError)) return intl.formatMessage({ id: generic })
    if (reason.status === 409) {
      return intl.formatMessage({ id: action === 'publish' ? 'content.publishConflict' : 'content.unarchiveConflict' })
    }
    if (reason.status !== 422) return intl.formatMessage({ id: generic })
    const missingId = reason.body.field === 'outcome'
      ? 'content.publishNeedsOutcome'
      : reason.body.field === 'title'
        ? 'content.publishNeedsTitle'
        : 'content.publishNeedsContent'
    return intl.formatMessage(
      { id: action === 'publish' ? 'content.publishRefused' : 'content.unarchiveRefused' },
      { reason: intl.formatMessage({ id: missingId }) },
    )
  }
}

export function Content() {
  const navigate = useNavigate()
  const intl = useIntl()
  const [params, setParams] = useSearchParams()
  const rawStatus = params.get('status')
  const status: StatusFilter = STATUSES.includes(rawStatus as StatusFilter) ? rawStatus as StatusFilter : 'all'
  const folder: FolderFilter = params.get('folder') || 'all'
  const search = params.get('q') ?? ''
  const deferredSearch = useDeferredValue(search.trim())
  /**
   * Whatever the last row action had to say, and which row it was about.
   *
   * The `courseId` is what lets the message be rendered on the row that produced it
   * instead of only at the top of the screen, where a long library puts it out of sight.
   * `null` means "not about a row that is on the list" — a delete whose row has already
   * gone — and only then does the page-level slot show it.
   */
  const [actionError, setActionError] = useState<{ courseId: string | null; message: string } | null>(null)
  const [assigningFolder, setAssigningFolder] = useState<CourseFolder | null>(null)
  const [retryingId, setRetryingId] = useState<string | null>(null)
  const archivedView = status === ARCHIVED
  const publishRefusal = usePublishRefusal()
  const foldersQuery = useCourseFolders()
  const coursesQuery = useCourses({
    // `failed` filters on the creation run, not on the course's own status.
    status: status === 'all' || status === 'failed' ? undefined : status,
    generationState: status === 'failed' ? 'failed' : undefined,
    search: deferredSearch || undefined,
    folderId: folder !== 'all' && folder !== 'unorganized' ? folder : undefined,
    unorganized: folder === 'unorganized',
    includeArchived: false,
  })
  // Both counts drive the folder sidebar, so both have to count what the list shows:
  // a "Todos 12" over a list of nine is the archived courses leaking back in as a number.
  const totalQuery = useCourses({ limit: 1, includeArchived: false })
  const unorganizedQuery = useCourses({ unorganized: true, limit: 1, includeArchived: false })
  // One row of one, read for `total`: the entry needs the count, never the courses.
  const archivedQuery = useCourses({ status: ARCHIVED, limit: 1 })
  const archivedCount = archivedQuery.data?.total ?? 0
  const updateCourse = useUpdateCourse()
  const publishCourse = usePublishCourse()
  const archiveCourse = useArchiveCourse()
  const unarchiveCourse = useUnarchiveCourse()
  const deletion = useCourseDeletion()
  const courses = coursesQuery.data?.items ?? []
  const folders = foldersQuery.data ?? []

  function updateParams(changes: Record<string, string | null>) {
    setParams((current) => {
      const next = new URLSearchParams(current)
      Object.entries(changes).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key))
      return next
    }, { replace: true })
  }

  function failRow(course: CourseRead, message: string) {
    setActionError({ courseId: course.id, message })
  }

  /** One row, one message: whichever of the two owners of a failure has one to show. */
  function resetErrors() {
    setActionError(null)
    deletion.clearError()
  }

  function rowError(course: CourseRead): string | null {
    if (deletion.error?.courseId === course.id) return deletion.error.message
    if (actionError?.courseId === course.id) return actionError.message
    return null
  }

  async function moveCourse(course: CourseRead, folderId: string | null) {
    resetErrors()
    try {
      await updateCourse.mutateAsync({ id: course.id, payload: { folder_id: folderId } })
    } catch (reason) {
      // A 404 here is the folder, not the course: somebody deleted it between this page
      // being fetched and the click. The server says so in English, so it is translated.
      failRow(course, reason instanceof ApiError && reason.status === 404
        ? intl.formatMessage({ id: 'content.moveErrorFolderGone' })
        : intl.formatMessage({ id: 'content.moveError' }))
    }
  }

  /**
   * Publishing from the row used to be `publishCourse.mutate(id)` and nothing else.
   *
   * A refused publish — the same missing outcome that shows up under *Desarchivar* —
   * therefore changed nothing anywhere on the screen. Silence is the one answer a button
   * must never give.
   */
  async function publish(course: CourseRead) {
    resetErrors()
    try {
      await publishCourse.mutateAsync(course.id)
    } catch (reason) {
      failRow(course, publishRefusal(reason, 'publish'))
    }
  }

  async function archive(course: CourseRead) {
    resetErrors()
    try {
      await archiveCourse.mutateAsync(course.id)
    } catch (reason) {
      failRow(course, reason instanceof ApiError && reason.status === 409
        ? intl.formatMessage({ id: 'content.archiveConflict' })
        : intl.formatMessage({ id: 'content.archiveError' }))
    }
  }

  /**
   * Re-run the server-side tail of creation on the course that already exists.
   *
   * Deliberately not "create it again": the row, its schema and its knowledge packs are
   * all still there, and starting over is what left the tester with two courses. The
   * endpoint is idempotent, so this is safe to press twice.
   */
  async function retryCreation(course: CourseRead) {
    resetErrors()
    setRetryingId(course.id)
    try {
      await startCourseFinalization(course.id)
      navigate(`/admin/crear-curso?course=${course.id}`)
    } catch {
      // No branch on the server's message: `POST …/schema/finalize` answers 404 for a
      // course that is gone and 500 for a pipeline that broke, and neither is something
      // the admin can act on differently. The one useful instruction is "try again".
      failRow(course, intl.formatMessage({ id: 'content.retryCreationError' }))
    } finally {
      setRetryingId(null)
    }
  }

  /**
   * Unarchiving re-runs the publish checks, so it can be refused for a reason that has
   * nothing to do with the archive — see `CourseService.unarchive` for why re-running
   * them is right. `usePublishRefusal` says it from the admin's side of that.
   */
  async function unarchive(course: CourseRead) {
    resetErrors()
    try {
      await unarchiveCourse.mutateAsync(course.id)
    } catch (reason) {
      failRow(course, publishRefusal(reason, 'unarchive'))
    }
  }

  // The archive is a place, not a filter — "clear filters" must not be the way out of it,
  // and it must not empty the screen of the only heading that says where you are.
  const hasFilters = (!archivedView && status !== 'all') || folder !== 'all' || search.trim().length > 0
  function clearFilters() {
    setParams(archivedView ? { status: ARCHIVED } : {}, { replace: true })
  }
  /**
   * The entry belongs to the *normal* view, the way it does in a chat app.
   *
   * Not next to a search's results (the count answers a different question than the
   * search did), not inside a folder (it counts the whole organization), and not inside
   * the archive itself.
   */
  const showArchivedEntry = !archivedView && status === 'all' && folder === 'all' && !deferredSearch && archivedCount > 0

  /**
   * Nothing to show, and the three different reasons for it.
   *
   * An empty archive is not an empty library: "Aún no hay cursos / Crea el primero" is
   * both wrong and a dead end in there, because creating a course does not put one in
   * the archive.
   */
  const emptyState = hasFilters
    ? { title: 'content.noResultsTitle', description: 'content.noResultsDesc', action: { label: intl.formatMessage({ id: 'content.clearFilters' }), onClick: clearFilters } }
    : archivedView
      ? { title: 'content.archivedEmptyTitle', description: 'content.archivedEmptyDesc', action: { label: intl.formatMessage({ id: 'content.archivedEmptyAction' }), onClick: () => updateParams({ status: null }) } }
      : { title: 'content.emptyTitle', description: 'content.emptyDesc', action: { label: intl.formatMessage({ id: 'content.emptyAction' }), onClick: () => navigate('/admin/crear-curso') } }

  // A failure whose row the admin can no longer see needs the slot at the top. The
  // dialog carries its own copy while it is open, so it is not repeated behind it.
  const failure = deletion.error ?? actionError
  const orphanError = failure && !deletion.pendingCourse && !courses.some((row) => row.id === failure.courseId)
    ? failure.message
    : null

  return (
    <div>
      <PageHeader
        title={intl.formatMessage({ id: 'content.libraryTitle' })}
        description={intl.formatMessage({ id: 'content.librarySubtitle' })}
        actions={<Button variant="primary" size="md" onClick={() => navigate('/admin/crear-curso')}><span className="flex items-center gap-1.5"><PlusIcon />{intl.formatMessage({ id: 'content.createNew' })}</span></Button>}
      />

      <div className="mt-5 grid gap-5 xl:grid-cols-[220px_minmax(0,1fr)]">
        <div>
          {foldersQuery.isLoading || totalQuery.isLoading || unorganizedQuery.isLoading ? <ShimmerSkeleton className="h-40 w-full" /> : foldersQuery.error ? (
            <div className="border border-border rounded-lg p-4"><p className="text-sm text-danger">{intl.formatMessage({ id: 'content.folderLoadError' })}</p></div>
          ) : <CourseFolderSidebar folders={folders} selected={folder} totalCount={totalQuery.data?.total ?? 0} unorganizedCount={unorganizedQuery.data?.total ?? 0} onSelect={(value) => updateParams({ folder: value === 'all' ? null : value })} onAssign={setAssigningFolder} />}
        </div>

        <section className="min-w-0" aria-label={intl.formatMessage({ id: 'content.courses' })}>
          {archivedView && (
            /* The archive announces itself, and offers the way back. Every course in here
               is archived, so the status control below would have nothing left to say. */
            <div className="mb-3 flex items-center gap-2">
              <button type="button" onClick={() => updateParams({ status: null })} className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:text-primary-hover cursor-pointer">
                <ChevronLeftIcon />
                {intl.formatMessage({ id: 'content.archivedBack' })}
              </button>
              <span className="text-text-muted" aria-hidden="true">/</span>
              <h2 className="flex items-center gap-1.5 text-sm font-semibold text-text"><ArchiveBoxIcon size={16} />{intl.formatMessage({ id: 'content.archived' })}</h2>
            </div>
          )}
          <div className={`grid gap-3 ${archivedView ? '' : 'md:grid-cols-[minmax(0,1fr)_180px]'}`}>
            <SearchField label={intl.formatMessage({ id: 'content.searchLabel' })} value={search} onChange={(event) => updateParams({ q: event.target.value || null })} placeholder={intl.formatMessage({ id: 'content.searchPlaceholder' })} />
            {!archivedView && (
              <Select label={intl.formatMessage({ id: 'content.statusFilter' })} hideLabel value={status} onChange={(event) => updateParams({ status: event.target.value === 'all' ? null : event.target.value })}>
                  <option value="all">{intl.formatMessage({ id: 'content.statusAll' })}</option>
                  <option value="published">{intl.formatMessage({ id: 'content.published' })}</option>
                  <option value="draft">{intl.formatMessage({ id: 'content.drafts' })}</option>
                  <option value="failed">{intl.formatMessage({ id: 'content.statusFailed' })}</option>
              </Select>
            )}
          </div>
          <div className="mt-3 flex items-center justify-between gap-3 min-h-6">
            <p className="text-xs text-text-muted">{coursesQuery.data && intl.formatMessage({ id: 'content.resultsCount' }, { count: coursesQuery.data.total })}</p>
            {hasFilters && <button type="button" onClick={clearFilters} className="text-xs font-medium text-primary hover:text-primary-hover">{intl.formatMessage({ id: 'content.clearFilters' })}</button>}
          </div>
          {/* Only for a failure whose row is not on the list any more; everything else
              is rendered on the row itself, where the admin is looking. */}
          {orphanError && <p role="alert" className="mt-2 border border-danger/30 rounded-lg px-3 py-2 text-sm text-danger">{orphanError}</p>}

          <div className="mt-2">
            {coursesQuery.isLoading ? <LibrarySkeleton /> : coursesQuery.error ? (
              <Card><EmptyState title={intl.formatMessage({ id: 'content.loadError' })} description={apiErrorMessage(intl, coursesQuery.error, 'content.loadErrorRetry')} /></Card>
            ) : courses.length === 0 ? (
              <Card><EmptyState title={intl.formatMessage({ id: emptyState.title })} description={intl.formatMessage({ id: emptyState.description })} action={emptyState.action} /></Card>
            ) : (
              <motion.div className="space-y-2" initial="hidden" animate="visible" variants={staggerContainer}>
                {courses.map((course) => <CourseRow key={course.id} course={course} folders={folders} moving={updateCourse.isPending} onMove={moveCourse} onOpen={navigate} onPublish={publish} onArchive={archive} onUnarchive={unarchive} onDelete={deletion.requestDelete} onRetry={retryCreation} publishing={publishCourse.isPending} archiving={archiveCourse.isPending} unarchiving={unarchiveCourse.isPending && unarchiveCourse.variables === course.id} deleting={deletion.isDeleting(course.id)} retrying={retryingId === course.id} error={rowError(course)} />)}
              </motion.div>
            )}
            {showArchivedEntry && (
              /* The way into the archive, and the only place it is mentioned. Below the
                 courses rather than above them: the library is what the admin came for,
                 and the entry is a footnote that happens to be clickable. */
              <button
                type="button"
                onClick={() => updateParams({ status: ARCHIVED })}
                className="mt-2 w-full flex items-center gap-3 border border-border rounded-lg px-5 py-3 text-left transition-colors cursor-pointer hover:bg-bg-muted"
              >
                <span className="text-text-muted shrink-0"><ArchiveBoxIcon size={16} /></span>
                <span className="flex-1 text-sm font-medium text-text">{intl.formatMessage({ id: 'content.archived' })}</span>
                <span className="text-xs tabular-nums text-text-muted">{archivedCount}</span>
                <span className="text-text-muted shrink-0"><ChevronRightIcon /></span>
              </button>
            )}
          </div>
        </section>
      </div>
      {assigningFolder && <FolderAssignmentDialog folder={assigningFolder} onClose={() => setAssigningFolder(null)} />}
      {deletion.dialog}
    </div>
  )
}
