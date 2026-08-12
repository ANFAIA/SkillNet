import { useIntl } from 'react-intl'
import { CourseMediaGenerator } from './CourseMediaGenerator'
import { CourseMediaLibrary } from './CourseMediaLibrary'

/** Admin composition: generation controls plus the operational artifact library. */
export function CourseOverviews({ courseId }: { courseId: string }) {
  const intl = useIntl()

  return (
    <div>
      <div className="mb-4">
        <h3 className="text-base font-medium text-text">
          {intl.formatMessage({ id: 'overviews.title' })}
        </h3>
        <p className="text-sm text-text-secondary">
          {intl.formatMessage({ id: 'overviews.subtitle' })}
        </p>
      </div>
      <CourseMediaGenerator courseId={courseId} />
      <CourseMediaLibrary courseId={courseId} operational />
    </div>
  )
}
