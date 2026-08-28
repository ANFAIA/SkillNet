import { useState } from 'react'
import { useIntl } from 'react-intl'
import { Button, Input, Modal } from '../ui'
import type { CourseDeletionImpact } from '../../api/enrollments'
import type { CourseRead } from '../../types'

interface CourseDeleteDialogProps {
  course: CourseRead
  impact: CourseDeletionImpact
  deleting: boolean
  /** The server's reason when a delete came back refused, shown inside the dialog. */
  error: string | null
  onConfirm: () => void
  onClose: () => void
}

/**
 * The warning in front of a delete that reaches other people's records.
 *
 * The ordinary case never gets here: a course nobody finished is confirmed with the same
 * `window.confirm` as the rest of this screen, because the damage is the admin's own
 * work. This dialog is for the case where it is not — somebody completed the course, so
 * deleting it removes a record of training that person did, and no amount of undo brings
 * it back.
 *
 * Two things it does that a confirm cannot. It says the **exact numbers**, because
 * "affects enrollments" and "affects 34 enrollments, 12 of them completed" are different
 * decisions. And it asks for the **course title to be typed back**, which is the cheapest
 * known way to turn a reflex into a deliberate act: a confirm is dismissed with the same
 * gesture whether it was read or not.
 */
export function CourseDeleteDialog({ course, impact, deleting, error, onConfirm, onClose }: CourseDeleteDialogProps) {
  const intl = useIntl()
  const [typed, setTyped] = useState('')
  // Trimmed on both sides: a trailing space pasted with the title is not a different
  // answer, and the check is a deliberateness gate, not a spelling test.
  const matches = typed.trim() === course.title.trim()

  return (
    <Modal open onClose={onClose} size="sm">
      <h2 className="text-base font-semibold text-text pr-8">
        {intl.formatMessage({ id: 'content.courseDeleteHeavyTitle' }, { title: course.title })}
      </h2>
      <p className="mt-3 text-sm text-text-secondary">
        {intl.formatMessage(
          { id: 'content.courseDeleteHeavyBody' },
          { total: impact.total, completed: impact.completed },
        )}
      </p>
      <p className="mt-2 text-sm text-text-secondary">
        {intl.formatMessage({ id: 'content.courseDeleteHeavyIrreversible' })}
      </p>

      <div className="mt-5">
        <Input
          autoFocus
          label={intl.formatMessage({ id: 'content.courseDeleteTypeTitle' }, { title: course.title })}
          value={typed}
          autoComplete="off"
          placeholder={course.title}
          onChange={(event) => setTyped(event.target.value)}
        />
      </div>

      {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}

      <div className="mt-5 flex justify-end gap-2">
        <Button variant="secondary" size="md" onClick={onClose} disabled={deleting}>
          {intl.formatMessage({ id: 'content.folderCancel' })}
        </Button>
        <Button variant="danger" size="md" onClick={onConfirm} disabled={!matches || deleting}>
          {deleting
            ? intl.formatMessage({ id: 'content.courseDeleting' })
            : intl.formatMessage({ id: 'content.courseDeleteHeavyConfirm' })}
        </Button>
      </div>
    </Modal>
  )
}
