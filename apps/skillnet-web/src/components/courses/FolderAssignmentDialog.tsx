import { useState } from 'react'
import { useIntl } from 'react-intl'
import { useAssignCourseFolder, type CourseFolder } from '../../api/course-folders'
import { useUsers } from '../../api/users'
import { ApiError } from '../../api/client'
import { Button, Input, Modal } from '../ui'
import { ShimmerSkeleton } from '../ui/ShimmerSkeleton'

type FolderAssignmentDialogProps = {
  folder: CourseFolder
  onClose: () => void
}

export function FolderAssignmentDialog({ folder, onClose }: FolderAssignmentDialogProps) {
  const intl = useIntl()
  const users = useUsers({ role: 'employee', is_active: true })
  const assign = useAssignCourseFolder()
  const [selected, setSelected] = useState<string[]>([])
  const [deadline, setDeadline] = useState('')
  const employees = users.data?.items ?? []

  function toggle(userId: string) {
    setSelected((current) => current.includes(userId) ? current.filter((id) => id !== userId) : [...current, userId])
  }

  return (
    <Modal open onClose={onClose} size="md">
      <h2 className="text-lg font-semibold text-text">{intl.formatMessage({ id: 'content.assignFolderTitle' }, { name: folder.name })}</h2>
      <p className="mt-1 text-sm text-text-secondary">{intl.formatMessage({ id: 'content.assignFolderDescription' })}</p>
      {assign.data ? (
        <div className="mt-5">
          <p className="text-sm text-text">{intl.formatMessage({ id: 'content.assignFolderSuccess' }, { enrollments: assign.data.created_count, courses: assign.data.course_count })}</p>
          {assign.data.skipped_existing_count > 0 && <p className="mt-1 text-sm text-text-muted">{intl.formatMessage({ id: 'content.assignFolderSkipped' }, { count: assign.data.skipped_existing_count })}</p>}
          <Button className="mt-5" onClick={onClose}>{intl.formatMessage({ id: 'content.assignFolderDone' })}</Button>
        </div>
      ) : (
        <>
          <div className="mt-5 max-h-64 divide-y divide-border overflow-y-auto rounded-lg border border-border px-3">
            {users.isLoading ? <div className="space-y-3 py-4" aria-hidden="true"><ShimmerSkeleton className="h-10 w-full" /><ShimmerSkeleton className="h-10 w-full" /><ShimmerSkeleton className="h-10 w-full" /></div> : employees.map((employee) => (
              <label key={employee.id} className="flex cursor-pointer items-center gap-3 py-3">
                <input type="checkbox" checked={selected.includes(employee.id)} onChange={() => toggle(employee.id)} className="size-4 accent-primary" />
                <span className="min-w-0"><span className="block truncate text-sm font-medium text-text">{employee.full_name}</span><span className="block truncate text-xs text-text-muted">{employee.email}</span></span>
              </label>
            ))}
            {!users.isLoading && employees.length === 0 && <p className="py-4 text-sm text-text-muted">{intl.formatMessage({ id: 'content.assignFolderNoPeople' })}</p>}
          </div>
          <Input className="mt-4" label={intl.formatMessage({ id: 'content.assignmentDeadline' })} type="date" value={deadline} onChange={(event) => setDeadline(event.target.value)} />
          {assign.isError && <p role="alert" className="mt-3 text-sm text-danger">{assign.error instanceof ApiError ? assign.error.body.detail : intl.formatMessage({ id: 'content.assignFolderError' })}</p>}
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>{intl.formatMessage({ id: 'content.folderCancel' })}</Button>
            <Button disabled={selected.length === 0 || assign.isPending} onClick={() => assign.mutate({ id: folder.id, userIds: selected, deadline })}>{intl.formatMessage({ id: 'content.assignFolderAction' }, { count: folder.course_count ?? 0 })}</Button>
          </div>
        </>
      )}
    </Modal>
  )
}
