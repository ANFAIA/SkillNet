import { useEffect, useState } from 'react'
import { useIntl } from 'react-intl'

import {
  DidactComponentMount,
  type DidactHostPorts,
} from '../../../lib/didact'

type ProgressSnapshot = {
  status: 'not_started' | 'in_progress' | 'completed'
  progress: number
  level: 'beginner' | 'intermediate' | 'advanced'
}

export function HostProgressActivity({
  activityId,
  componentId,
  componentProps,
  ports,
}: {
  activityId: string
  componentId: string
  componentProps: Readonly<Record<string, unknown>>
  ports: DidactHostPorts
}) {
  const intl = useIntl()
  const [snapshot, setSnapshot] = useState<ProgressSnapshot>()
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setFailed(false)
    if (!ports.progress) {
      setFailed(true)
      return () => controller.abort()
    }
    void ports.progress
      .read({ organizationId: '', courseId: '' }, componentId, controller.signal)
      .then((record) => {
        setSnapshot({
          status: record?.status ?? 'not_started',
          progress: record?.progress ?? 0,
          level:
            record?.evidence &&
            typeof record.evidence === 'object' &&
            !Array.isArray(record.evidence) &&
            (record.evidence.level === 'beginner' ||
              record.evidence.level === 'intermediate' ||
              record.evidence.level === 'advanced')
              ? record.evidence.level
              : 'beginner',
        })
      })
      .catch(() => setFailed(true))
    return () => controller.abort()
  }, [componentId, ports.progress])

  if (failed) {
    return (
      <div role="alert" data-didact-progress-status="failed">
        {intl.formatMessage({ id: 'activity.progressReadError' })}
      </div>
    )
  }
  if (!snapshot) {
    return (
      <div role="status" data-didact-progress-status="loading">
        {intl.formatMessage({ id: 'activity.progressLoading' })}
      </div>
    )
  }

  const mountedProps =
    componentId === 'didact.mastery-badge'
      ? {
          ...componentProps,
          level: snapshot.level,
          percent: snapshot.progress,
          interactive: false,
        }
      : {
          ...componentProps,
          kind: componentProps.kind === 'skill' ? 'skill' : 'lesson',
          value: snapshot.progress,
          max: 100,
        }

  return (
    <div data-didact-progress-activity={activityId}>
      <DidactComponentMount
        componentId={componentId}
        componentProps={mountedProps}
        ports={ports}
      />
    </div>
  )
}
