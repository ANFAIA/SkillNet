import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useIntl } from 'react-intl'
import { Button, ProgressBar } from '../ui'
import { CourseIndex } from './CourseIndex'
import { CourseMediaGenerator } from './CourseMediaGenerator'
import { CourseMediaLibrary } from './CourseMediaLibrary'
import { CourseChatPanel } from './CourseChatPanel'
import { hasStartedCourse, selectResumeNode } from '../../features/resume/selectResumeNode'
import { useCoursePath, nodePath } from '../../lib/courseRoutes'
import type { CourseDetail, NodeList } from '../../types'

interface CourseOverviewProps {
  course: CourseDetail
  nodes: NodeList
}

export function CourseOverview({ course, nodes }: CourseOverviewProps) {
  const intl = useIntl()
  const navigate = useNavigate()
  const { state: routeState } = useLocation()
  const [chatOpen, setChatOpen] = useState(false)
  const orderedNodes = useMemo(
    () => [...nodes.nodes].sort((a, b) => a.position - b.position),
    [nodes.nodes],
  )
  /**
   * The node "Continuar" opens. The chain of `find`s this replaced looked for
   * `state === 'learning'` first, which is only reachable by answering a graded item
   * (rule 0 of §7.3) — so every expository node, and every node read without answering,
   * stayed `not_started` and the button always reopened the first one. The decision now
   * comes from `first_seen_at`, and from the server's own `next_node_id` when nothing
   * unfinished has been opened yet; the reasoning is in `selectResumeNode`.
   */
  const target = useMemo(
    () => selectResumeNode(orderedNodes, nodes.next_node_id),
    [orderedNodes, nodes.next_node_id],
  )
  const courseBasePath = useCoursePath(course.id)
  const nodeHref = target ? nodePath(courseBasePath, target.id) : null

  /**
   * "Continuar donde lo dejaste" elsewhere in the app navigates here with
   * `state.resume`, and this forwards it to the node. It is done here rather than in the
   * caller because the caller (the home hero, a course row) has no node list and getting
   * one would cost a request per course. `replace` so the browser Back goes where the
   * learner came from, and once per mount so a Back into this page does not bounce.
   */
  const forwardedRef = useRef(false)
  const resumeIntent = (routeState as { resume?: boolean } | null)?.resume === true
  useEffect(() => {
    if (!resumeIntent || forwardedRef.current || !nodeHref) return
    forwardedRef.current = true
    navigate(nodeHref, { replace: true })
  }, [resumeIntent, nodeHref, navigate])

  // Same three existing labels, but "Continuar" is no longer gated on progress alone:
  // `progress_percent` counts nodes the server calls done, and a node is not done until
  // it is stamped, so somebody part-way through their first lesson was offered "Empezar"
  // over a button that reopens it. Having been served a node is enough to have started.
  const actionLabel = nodes.progress_percent >= 100
    ? intl.formatMessage({ id: 'courseview.review' })
    : nodes.progress_percent > 0 || hasStartedCourse(orderedNodes)
      ? intl.formatMessage({ id: 'courseview.continue' })
      : intl.formatMessage({ id: 'courseview.start' })

  return (
    <div>
      <header className="mb-7">
        <h1 className="text-2xl font-semibold leading-tight text-text">{course.title}</h1>
        {course.description && (
          <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">
            {course.description}
          </p>
        )}
        {course.outcome && (
          <p className="mt-1 text-sm text-text-muted">
            {intl.formatMessage({ id: 'preview.objective' }, { outcome: course.outcome })}
          </p>
        )}

        <div className="mt-5 flex flex-wrap items-center gap-4 border-y border-border py-4">
          <div className="min-w-0 basis-64 flex-1">
            <div className="mb-2 flex items-center justify-between gap-4">
              <span className="text-sm font-medium text-text">
                {intl.formatMessage({ id: 'courseview.progress' })}
              </span>
              <span className="shrink-0 text-sm font-semibold tabular-nums text-text">
                {Math.round(nodes.progress_percent)}%
              </span>
            </div>
            <ProgressBar value={nodes.progress_percent} variant="auto" size="sm" />
          </div>
          <div className="flex w-full gap-2 sm:w-auto">
            <Button size="lg" variant="secondary" className="min-w-0 flex-1 gap-2 sm:flex-none" onClick={() => setChatOpen(true)}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" />
              </svg>
              {intl.formatMessage({ id: 'courseChat.action' })}
            </Button>
            <Button
              size="lg"
              className="min-w-0 flex-1 gap-2 sm:flex-none"
              disabled={!nodeHref}
              onClick={() => nodeHref && navigate(nodeHref)}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M8 5.5v13l10-6.5z" />
              </svg>
              {actionLabel}
            </Button>
          </div>
        </div>
      </header>

      <div className="grid items-start gap-6 [grid-template-columns:repeat(auto-fit,minmax(min(100%,22rem),1fr))]">
        <div className="min-w-0">
          <CourseIndex courseId={course.id} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="mb-4">
            <h3 className="text-base font-medium text-text">
              {intl.formatMessage({ id: 'overviews.libraryTitle' })}
            </h3>
            <p className="text-sm text-text-secondary">
              {intl.formatMessage({ id: 'overviews.librarySubtitle' })}
            </p>
          </div>
          {course.can_generate_artifacts && <CourseMediaGenerator courseId={course.id} />}
          <CourseMediaLibrary courseId={course.id} operational={!!course.can_generate_artifacts} />
        </div>
      </div>

      <CourseChatPanel
        open={chatOpen}
        onClose={() => setChatOpen(false)}
        courseId={course.id}
        courseTitle={course.title}
      />
    </div>
  )
}
