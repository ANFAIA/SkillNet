import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useIntl } from 'react-intl'
import { useNavigate } from 'react-router-dom'
import { useCourses } from '../../api/courses'
import { isServedRender, useCourseNodes, useNodeRender } from '../../api/nodes'
import { Button, Card, EmptyState, PageHeader, Skeleton } from '../../components/ui'
import { SegmentedControl } from '../../components/settings/SegmentedControl'
import { UiSpecRenderer } from '../../components/courses/UiSpecRenderer'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { duration, ease } from '../../lib/motion'

type PreviewPref = 'audio' | 'visual'

// Same morph convention as CreateCourse/Setup: the container box springs to its new
// size via a shared layoutId, and inner content is opacity-only (no blur, never
// scaled) and fades in only once the spring has had time to settle — so the text is
// never visible while the box is still resizing, which is what avoids the distortion
// a bare `layout` on a text-bearing box causes.
const cardMorphTransition = { type: 'spring' as const, stiffness: 200, damping: 28 }
const innerFadeOut = { exit: { opacity: 0, transition: { duration: duration.fast, ease: ease.base } } }
const innerFadeIn = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: duration.normal, ease: ease.base, delay: 0.35 } },
}

/**
 * `layout` animates a size change with a transform-scale trick and resolves the real
 * DOM box to its final height immediately — so anything below in normal flow (the
 * note, the CTA banner) snaps to its new position at once while only the card *looks*
 * like it is still resizing, reading as "everything jumps". Measuring the real content
 * height and animating the wrapper's actual `height` (with `overflow: hidden`) instead
 * means the box's footprint changes for real, frame by frame, so anything below
 * reflows in the same smooth motion instead of snapping ahead of it.
 */
function useMeasuredHeight<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [height, setHeight] = useState<number>()
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    // `offsetHeight` rounds to an integer; when the real rendered height is a
    // fraction of a pixel above that (sub-pixel layout, common with borders), the
    // overflow-hidden wrapper below clips the last sliver of the card's bottom
    // border. getBoundingClientRect() keeps the fraction, and rounding up (not
    // to-nearest) guarantees the wrapper is never a hair shorter than the content.
    const update = () => setHeight(Math.ceil(el.getBoundingClientRect().height))
    update()
    const observer = new ResizeObserver(update)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  return { ref, height }
}

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
  const reduce = useReducedMotion()
  const [pref, setPref] = useState<PreviewPref>('audio')
  const { ref: contentRef, height: contentHeight } = useMeasuredHeight<HTMLDivElement>()

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

      <div className="mt-5 mb-4" data-tour="demo-preview-toggle">
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

      {/* The wrapper animates its real `height` to the content's measured height
          (useMeasuredHeight), not framer's `layout` — a real height change makes
          anything below reflow in the same smooth motion instead of snapping to its
          final position while only the card looks like it's still resizing. Content
          is opacity-only (never scaled) and, with a real height animating in, doesn't
          need the fade-in delay a `layout` scale-hack would — it's simply revealed. */}
      <motion.div
        style={{ overflow: 'hidden' }}
        animate={{ height: reduce || contentHeight === undefined ? 'auto' : contentHeight }}
        transition={reduce ? { duration: 0 } : cardMorphTransition}
      >
        <div ref={contentRef}>
          <Card>
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={loading || (!program && render.isLoading) ? 'loading' : program ? pref : 'empty'}
                {...(reduce ? {} : { ...innerFadeIn, ...innerFadeOut })}
              >
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
              </motion.div>
            </AnimatePresence>
          </Card>
        </div>
      </motion.div>

      <p className="mt-3 flex items-center gap-1.5 text-xs text-primary">
        <span aria-hidden>✦</span>
        {intl.formatMessage({
          id: pref === 'audio' ? 'demoLesson.noteAudio' : 'demoLesson.noteVisual',
        })}
      </p>

      {/* Lead out of the demo and into the first real win (docs/design/onboarding.md
          §3.2): the guided flow always ends pointing at "create your first course". */}
      <div className="mt-6 flex items-center justify-between gap-3 rounded-xl border border-primary/40 bg-gradient-to-r from-primary/10 to-success/10 p-4" data-tour="demo-create-cta">
        <p className="text-sm text-text-secondary">
          {intl.formatMessage({ id: 'demoLesson.createHint' })}
        </p>
        <Button variant="primary" onClick={() => navigate('/admin/crear-curso')}>
          {intl.formatMessage({ id: 'demoLesson.createCta' })}
        </Button>
      </div>
    </div>
  )
}
