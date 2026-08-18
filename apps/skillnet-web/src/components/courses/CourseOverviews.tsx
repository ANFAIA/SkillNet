import { useState } from 'react'
import { useIntl } from 'react-intl'
import { CourseMediaGenerator } from './CourseMediaGenerator'
import { CourseMediaLibrary } from './CourseMediaLibrary'
import { NodeMediaDialog } from './NodeMediaDialog'
import { CourseMediaIcon } from './CourseMediaIcon'

/** Admin composition: generation controls plus the operational artifact library. */
export function CourseOverviews({ courseId }: { courseId: string }) {
  const intl = useIntl()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [origin, setOrigin] = useState<DOMRect | null>(null)

  return (
    <div>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-medium text-text">
            {intl.formatMessage({ id: 'overviews.title' })}
          </h3>
          <p className="text-sm text-text-secondary">
            {intl.formatMessage({ id: 'overviews.subtitle' })}
          </p>
        </div>
        <button
          type="button"
          onClick={(event) => {
            setOrigin(event.currentTarget.getBoundingClientRect())
            setDialogOpen(true)
          }}
          className="inline-flex shrink-0 cursor-pointer items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm font-medium text-text hover:border-primary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
        >
          <CourseMediaIcon kind="podcast" size={16} />
          {intl.formatMessage({ id: 'overviews.node.cta' })}
        </button>
      </div>
      <CourseMediaGenerator courseId={courseId} />
      <CourseMediaLibrary courseId={courseId} operational />
      <NodeMediaDialog
        courseId={courseId}
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        origin={origin}
      />
    </div>
  )
}
