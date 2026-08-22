import { useEffect, useMemo, useState } from 'react'
import { useIntl } from 'react-intl'
import { useNavigate } from 'react-router-dom'
import { useCourses } from '../../api/courses'
import { isServedRender, useCourseNodes, useNodeRender } from '../../api/nodes'
import { Card, EmptyState, PageHeader, Skeleton } from '../../components/ui'
import { SegmentedControl } from '../../components/settings/SegmentedControl'
import { UiSpecRenderer } from '../../components/courses/UiSpecRenderer'

type PreviewPref = 'audio' | 'visual'

/**
 * The onboarding "aha" as a lightweight, effortless comparison — not the full lesson
 * runner (docs/design/onboarding.md §3.2). It shows the demo course's showcase lesson
 * rendered by the REAL `UiSpecRenderer` and lets the admin flip it between two learner
 * preferences with the SAME `SegmentedControl` used in Ajustes.
 *
 * Deliberately not NodeView: this is "look and compare", so there is no intro gate, no
 * step pagination and no navigation — the whole lesson renders in one scrollable view,
 * and toggling the learner swaps the pre-baked variant in place (both are served as
 * instant cache hits via `?preview_pref`, no generation). That also sidesteps the
 * stepper reset that made switching feel like being sent back to screen one.
 */
export function DemoLesson() {
  const intl = useIntl()
  const navigate = useNavigate()
  const [pref, setPref] = useState<PreviewPref>('audio')

  // Find the per-org pre-baked demo course, then its showcase (first) node.
  const courses = useCourses()
  const demoCourse = useMemo(
    () => courses.data?.items.find((c) => c.is_demo),
    [courses.data],
  )
  const nodes = useCourseNodes(demoCourse?.id, { enabled: !!demoCourse })
  const showcaseNode = useMemo(() => {
    const list = nodes.data?.nodes ?? []
    return [...list].sort((a, b) => a.position - b.position)[0]
  }, [nodes.data])

  const render = useNodeRender(showcaseNode?.id, {
    enabled: !!showcaseNode,
    previewPref: pref,
  })
  const served = isServedRender(render.data) ? render.data : null
  const program = served?.program ?? null

  // Warm the other variant so the first toggle is instant too.
  useNodeRender(showcaseNode?.id, {
    enabled: !!showcaseNode,
    previewPref: pref === 'audio' ? 'visual' : 'audio',
  })

  const loading = courses.isLoading || (!!demoCourse && nodes.isLoading)
  const missing = !courses.isLoading && !demoCourse

  // Keep focus on this being a demo the admin looks at; nothing to submit or complete.
  useEffect(() => {
    document.title = 'SkillNet — demo'
  }, [])

  if (missing) {
    return (
      <EmptyState
        title={intl.formatMessage({ id: 'demoLesson.missingTitle' })}
        description={intl.formatMessage({ id: 'demoLesson.missingDesc' })}
        action={{
          label: intl.formatMessage({ id: 'demoLesson.backToContent' }),
          onClick: () => navigate('/admin/contenido'),
        }}
      />
    )
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader
        title={intl.formatMessage({ id: 'demoLesson.title' })}
        description={intl.formatMessage({ id: 'demoLesson.subtitle' })}
      />

      <div className="mt-5 mb-4 max-w-sm" data-tour="demo-preview-toggle">
        <SegmentedControl<PreviewPref>
          value={pref}
          onChange={setPref}
          label={intl.formatMessage({ id: 'nodePreview.label' })}
          layoutId="demo-preview-pref"
          options={[
            { value: 'audio', label: intl.formatMessage({ id: 'nodePreview.audio' }) },
            { value: 'visual', label: intl.formatMessage({ id: 'nodePreview.visual' }) },
          ]}
        />
      </div>

      <Card>
        {loading || (!program && render.isLoading) ? (
          <div className="space-y-3">
            <Skeleton className="h-5 w-2/3" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-24 w-full rounded-lg" />
          </div>
        ) : program ? (
          <UiSpecRenderer program={program} nodeId={showcaseNode!.id} renderId={served?.render_id} />
        ) : (
          <p className="text-sm text-text-muted">{intl.formatMessage({ id: 'demoLesson.empty' })}</p>
        )}
      </Card>

      <p className="mt-3 flex items-center gap-1.5 text-xs text-primary">
        <span aria-hidden>✦</span>
        {intl.formatMessage({
          id: pref === 'audio' ? 'demoLesson.noteAudio' : 'demoLesson.noteVisual',
        })}
      </p>
    </div>
  )
}
