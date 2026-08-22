import { useDeferredValue, useState } from 'react'
import { useIntl } from 'react-intl'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Badge, Button, Card, EmptyState, PageHeader, SearchField, Select } from '../../components/ui'
import { ShimmerSkeleton } from '../../components/ui/ShimmerSkeleton'
import { CourseFolderSidebar, type FolderFilter } from '../../components/courses/CourseFolderSidebar'
import { CourseFolderPicker } from '../../components/courses/CourseFolderPicker'
import { FolderAssignmentDialog } from '../../components/courses/FolderAssignmentDialog'
import { useCourseFolders, type CourseFolder } from '../../api/course-folders'
import { useArchiveCourse, useCourses, usePublishCourse, useUpdateCourse } from '../../api/courses'
import { ApiError, post } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import { staggerContainer, staggerItem } from '../../lib/motion'
import type { CourseRead, CourseStatus } from '../../types'

const STATUSES = ['all', 'published', 'draft', 'archived'] as const
type StatusFilter = (typeof STATUSES)[number]

function useStatusConfig() {
  const intl = useIntl()
  const config: Record<string, { label: string; variant: 'accent' | 'warning' | 'primary' }> = {
    published: { label: intl.formatMessage({ id: 'status.published' }), variant: 'accent' },
    draft: { label: intl.formatMessage({ id: 'status.draft' }), variant: 'warning' },
    archived: { label: intl.formatMessage({ id: 'status.archived' }), variant: 'primary' },
  }
  return (status: CourseStatus) => config[status] ?? { label: status, variant: 'primary' as const }
}

function BookIcon() {
  return <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></svg>
}

function PlusIcon() {
  return <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>
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

function CourseRow({ course, folders, onMove, moving, onOpen, onPublish, onArchive, publishing, archiving }: {
  course: CourseRead
  folders: { id: string; name: string }[]
  onMove: (course: CourseRead, folderId: string | null) => void
  moving: boolean
  onOpen: (path: string) => void
  onPublish: (courseId: string) => void
  onArchive: (courseId: string) => void
  publishing: boolean
  archiving: boolean
}) {
  const intl = useIntl()
  const status = useStatusConfig()(course.status)
  const { user: currentUser } = useAuth()

  return (
    <Card variants={staggerItem}>
      <div className="flex min-w-0 flex-col gap-4 xl:flex-row xl:items-center">
        <div className="flex items-start gap-4 min-w-0 flex-1">
          <div className="text-text-muted shrink-0 mt-0.5"><BookIcon /></div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-sm font-medium text-text truncate min-w-0">{course.title}</span>
              <Badge variant={status.variant} badgeStyle="plain" className="shrink-0">{status.label}</Badge>
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1 text-xs text-text-muted">
              {course.delivery_mode === 'dynamic' ? (
                <><span className="text-primary font-medium">{intl.formatMessage({ id: 'content.dynamic' })}</span>{(course.node_count ?? 0) > 0 && <span>{intl.formatMessage({ id: 'content.nodesCount' }, { count: course.node_count })}</span>}</>
              ) : <span>{intl.formatMessage({ id: 'content.modulesCount' }, { count: course.module_count })}</span>}
              {course.folder_name && <span>{course.folder_name}</span>}
              {course.outcome && <span className="truncate max-w-xs">{course.outcome}</span>}
              <span>{intl.formatMessage({ id: 'content.updatedAt' }, { date: new Date(course.updated_at ?? course.created_at).toLocaleDateString() })}</span>
            </div>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-1 xl:justify-end">
          <CourseFolderPicker courseTitle={course.title} folderId={course.folder_id} folderName={course.folder_name} folders={folders} disabled={moving} onMove={(folderId) => onMove(course, folderId)} />
          {course.is_demo && <Button variant="primary" size="sm" data-tour="content-demo-open" onClick={() => onOpen('/admin/demo')}>{intl.formatMessage({ id: 'content.viewDemo' })}</Button>}
          {course.delivery_mode === 'dynamic' && !course.is_demo && <Button variant="ghost" size="sm" onClick={async () => { if (!currentUser) return; await post('/enrollments', { user_ids: [currentUser.id], course_id: course.id }).catch(() => {}); onOpen(`/admin/probar-curso/${course.id}`) }}>{intl.formatMessage({ id: 'content.test' })}</Button>}
          {course.module_count > 0 && course.delivery_mode !== 'dynamic' && <Button variant="ghost" size="sm" onClick={() => onOpen(`/admin/curso/${course.id}`)}>{intl.formatMessage({ id: 'content.viewCourse' })}</Button>}
          {canPublish(course) && <Button variant="ghost" size="sm" onClick={() => onPublish(course.id)} disabled={publishing}>{publishing ? intl.formatMessage({ id: 'preview.publishing' }) : intl.formatMessage({ id: 'preview.publish' })}</Button>}
          {course.status === 'published' && <Button variant="ghost" size="sm" onClick={() => onArchive(course.id)} disabled={archiving}>{archiving ? intl.formatMessage({ id: 'preview.archiving' }) : intl.formatMessage({ id: 'preview.archive' })}</Button>}
          <Button variant="ghost" size="sm" onClick={() => onOpen(`/admin/curso/${course.id}/ajustes`)}>{intl.formatMessage({ id: 'content.schema' })}</Button>
        </div>
      </div>
    </Card>
  )
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
  const [moveError, setMoveError] = useState<string | null>(null)
  const [assigningFolder, setAssigningFolder] = useState<CourseFolder | null>(null)
  const foldersQuery = useCourseFolders()
  const coursesQuery = useCourses({
    status: status === 'all' ? undefined : status,
    search: deferredSearch || undefined,
    folderId: folder !== 'all' && folder !== 'unorganized' ? folder : undefined,
    unorganized: folder === 'unorganized',
  })
  const totalQuery = useCourses({ limit: 1 })
  const unorganizedQuery = useCourses({ unorganized: true, limit: 1 })
  const updateCourse = useUpdateCourse()
  const publishCourse = usePublishCourse()
  const archiveCourse = useArchiveCourse()
  const courses = coursesQuery.data?.items ?? []
  const folders = foldersQuery.data ?? []

  function updateParams(changes: Record<string, string | null>) {
    setParams((current) => {
      const next = new URLSearchParams(current)
      Object.entries(changes).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key))
      return next
    }, { replace: true })
  }

  async function moveCourse(course: CourseRead, folderId: string | null) {
    setMoveError(null)
    try {
      await updateCourse.mutateAsync({ id: course.id, payload: { folder_id: folderId } })
    } catch (reason) {
      setMoveError(reason instanceof ApiError ? reason.body.detail : intl.formatMessage({ id: 'content.moveError' }))
    }
  }

  const hasFilters = status !== 'all' || folder !== 'all' || search.trim().length > 0

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
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_180px]">
            <SearchField label={intl.formatMessage({ id: 'content.searchLabel' })} value={search} onChange={(event) => updateParams({ q: event.target.value || null })} placeholder={intl.formatMessage({ id: 'content.searchPlaceholder' })} />
            <Select label={intl.formatMessage({ id: 'content.statusFilter' })} hideLabel value={status} onChange={(event) => updateParams({ status: event.target.value === 'all' ? null : event.target.value })}>
                <option value="all">{intl.formatMessage({ id: 'content.statusAll' })}</option>
                <option value="published">{intl.formatMessage({ id: 'content.published' })}</option>
                <option value="draft">{intl.formatMessage({ id: 'content.drafts' })}</option>
                <option value="archived">{intl.formatMessage({ id: 'content.archived' })}</option>
            </Select>
          </div>
          <div className="mt-3 flex items-center justify-between gap-3 min-h-6">
            <p className="text-xs text-text-muted">{coursesQuery.data && intl.formatMessage({ id: 'content.resultsCount' }, { count: coursesQuery.data.total })}</p>
            {hasFilters && <button type="button" onClick={() => setParams({}, { replace: true })} className="text-xs font-medium text-primary hover:text-primary-hover">{intl.formatMessage({ id: 'content.clearFilters' })}</button>}
          </div>
          {moveError && <p role="alert" className="mt-2 border border-danger/30 rounded-lg px-3 py-2 text-sm text-danger">{moveError}</p>}

          <div className="mt-2">
            {coursesQuery.isLoading ? <LibrarySkeleton /> : coursesQuery.error ? (
              <Card><EmptyState title={intl.formatMessage({ id: 'content.loadError' })} description={coursesQuery.error instanceof ApiError ? coursesQuery.error.body.detail : intl.formatMessage({ id: 'content.loadErrorRetry' })} /></Card>
            ) : courses.length === 0 ? (
              <Card><EmptyState title={intl.formatMessage({ id: hasFilters ? 'content.noResultsTitle' : 'content.emptyTitle' })} description={intl.formatMessage({ id: hasFilters ? 'content.noResultsDesc' : 'content.emptyDesc' })} action={hasFilters ? { label: intl.formatMessage({ id: 'content.clearFilters' }), onClick: () => setParams({}, { replace: true }) } : { label: intl.formatMessage({ id: 'content.emptyAction' }), onClick: () => navigate('/admin/crear-curso') }} /></Card>
            ) : (
              <motion.div className="space-y-2" initial="hidden" animate="visible" variants={staggerContainer}>
                {courses.map((course) => <CourseRow key={course.id} course={course} folders={folders} moving={updateCourse.isPending} onMove={moveCourse} onOpen={navigate} onPublish={(id) => publishCourse.mutate(id)} onArchive={(id) => archiveCourse.mutate(id)} publishing={publishCourse.isPending} archiving={archiveCourse.isPending} />)}
              </motion.div>
            )}
          </div>
        </section>
      </div>
      {assigningFolder && <FolderAssignmentDialog folder={assigningFolder} onClose={() => setAssigningFolder(null)} />}
    </div>
  )
}
