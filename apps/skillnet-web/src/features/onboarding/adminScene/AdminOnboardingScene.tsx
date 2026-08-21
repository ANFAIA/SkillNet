import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useIntl } from 'react-intl'
import { useNavigate } from 'react-router-dom'
import { Button, Card, MetricCard } from '../../../components/ui'
import { UiSpecRenderer } from '../../../components/courses/UiSpecRenderer'
import { useReducedMotion } from '../../../hooks/useReducedMotion'
import { duration, ease } from '../../../lib/motion'
import {
  SCENE_PERSONAS,
  SCENE_COURSE,
  SCENE_DEMO_STATS,
  type ScenePersonaKey,
} from './demoPrograms'

/**
 * The admin's first-run onboarding, as an interactive scene rather than a passive
 * spotlight tour (docs/design/onboarding.md §3.2). The empty company panel becomes
 * a stage the admin *touches*: open a real (bundled) lesson, switch it between two
 * learners to feel the personalization, watch the panel come alive, then hand off to
 * creating a real course. Nothing blocks; it is dismissible at any point and, once
 * dismissed, never returns (see `useAdminScene`).
 *
 * Zero backend dependency: the lesson programs and the figures are static fixtures
 * (`demoPrograms.ts`), so this renders instantly on a brand-new deployment.
 */

// ── Small count-up hook (respects reduced motion) ────────────
function useCountUp(target: number, run: boolean, reduce: boolean): number {
  const [value, setValue] = useState(0)
  useEffect(() => {
    if (!run) {
      setValue(0)
      return
    }
    if (reduce) {
      setValue(target)
      return
    }
    let raf = 0
    const startedAt = performance.now()
    const span = 900
    const tick = (now: number) => {
      const p = Math.min(1, (now - startedAt) / span)
      // easeOutCubic
      setValue(Math.round(target * (1 - Math.pow(1 - p, 3))))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, run, reduce])
  return value
}

function AnimatedMetric({
  label,
  icon,
  target,
  suffix = '',
  run,
  reduce,
}: {
  label: string
  icon: ReactNode
  target: number
  suffix?: string
  run: boolean
  reduce: boolean
}) {
  const value = useCountUp(target, run, reduce)
  return <MetricCard label={label} icon={icon} value={`${value}${suffix}`} />
}

// ── Minimal inline icons (mirroring the real Dashboard set) ──
const iconStroke = {
  width: 20,
  height: 20,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}
const UsersIcon = () => (
  <svg {...iconStroke}><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></svg>
)
const BookIcon = () => (
  <svg {...iconStroke}><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" /></svg>
)
const TargetIcon = () => (
  <svg {...iconStroke}><circle cx="12" cy="12" r="10" /><circle cx="12" cy="12" r="6" /><circle cx="12" cy="12" r="2" /></svg>
)
const ChartIcon = () => (
  <svg {...iconStroke}><line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" /></svg>
)

type Beat = 0 | 1 | 2 | 3

export function AdminOnboardingScene({ onDismiss }: { onDismiss: () => void }) {
  const intl = useIntl()
  const navigate = useNavigate()
  const reduce = useReducedMotion()
  const t = (id: string, values?: Record<string, string>) => intl.formatMessage({ id }, values)

  const [beat, setBeat] = useState<Beat>(0)
  const [lessonOpen, setLessonOpen] = useState(false)
  const [persona, setPersona] = useState<ScenePersonaKey>('ana')
  const [metricsLive, setMetricsLive] = useState(false)

  const activeProgram = useMemo(
    () => SCENE_PERSONAS.find((p) => p.key === persona)!.program,
    [persona],
  )

  const captions = [
    t('adminScene.cap.open'),
    t('adminScene.cap.switch'),
    t('adminScene.cap.panel'),
    t('adminScene.cap.create'),
  ]

  function openLesson() {
    if (lessonOpen) return
    setLessonOpen(true)
    setBeat(1)
  }
  function selectPersona(key: ScenePersonaKey) {
    setPersona(key)
    // Switching to the *other* learner is the "aha" — advance once it happens.
    if (key === 'bruno' && beat === 1) setBeat(2)
  }
  function revealPanel() {
    setMetricsLive(true)
    if (beat < 2) setBeat(2)
    // The CTA appears after the count-up would have settled.
    window.setTimeout(() => setBeat(3), reduce ? 0 : 1000)
  }

  const fade = reduce
    ? {}
    : { initial: { opacity: 0, scale: 0.985 }, animate: { opacity: 1, scale: 1 }, exit: { opacity: 0, scale: 0.99 }, transition: { duration: duration.normal, ease: ease.base } }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={onDismiss}
        className="absolute right-0 top-0 text-xs text-text-muted hover:text-text-secondary"
      >
        {t('adminScene.skip')}
      </button>

      {/* Header */}
      <div className="pr-28">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight text-text">{t('adminScene.greeting')}</h1>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/35 bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
            <span className="h-1.5 w-1.5 rounded-full bg-primary" />
            {t('adminScene.demoPill')}
          </span>
        </div>
        <p className="mt-1 text-sm text-text-secondary">{t('adminScene.subtitle')}</p>
      </div>

      {/* Beat progress */}
      <div className="mt-5 flex items-center gap-2">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-1.5 flex-1 overflow-hidden rounded-full bg-bg-subtle">
            <motion.div
              className="h-full rounded-full bg-primary"
              initial={false}
              animate={{ width: i <= beat ? '100%' : '0%' }}
              transition={reduce ? { duration: 0 } : { duration: duration.normal, ease: ease.base }}
            />
          </div>
        ))}
      </div>
      <p className="mt-2 text-sm text-text-secondary">{captions[beat]}</p>

      {/* Stage */}
      <Card className="mt-4 overflow-hidden !p-0">
        <button
          type="button"
          onClick={openLesson}
          className={`flex w-full items-center gap-4 p-4 text-left transition-colors ${
            lessonOpen ? 'cursor-default' : 'cursor-pointer hover:bg-bg-subtle'
          } ${!lessonOpen ? 'ring-2 ring-inset ring-primary/70' : ''}`}
        >
          <div className="grid h-14 w-20 shrink-0 place-items-center rounded-lg bg-gradient-to-br from-[#2a3f7a] to-[#5a3f8a] text-white/90">▶</div>
          <div className="min-w-0">
            <p className="truncate font-medium text-text">{t(SCENE_COURSE.titleId)}</p>
            <p className="truncate text-sm text-text-secondary">{t(SCENE_COURSE.subtitleId)}</p>
          </div>
          <span className="ml-auto shrink-0 rounded-full border border-success/40 bg-success/10 px-2.5 py-1 text-xs font-semibold text-success">
            {lessonOpen ? t('adminScene.course.opened') : t('adminScene.course.open')}
          </span>
        </button>

        {lessonOpen && (
          <div className="border-t border-border p-4">
            {/* Learner tabs */}
            <div className="mb-4 flex gap-2">
              {SCENE_PERSONAS.map((p) => {
                const on = p.key === persona
                return (
                  <button
                    key={p.key}
                    type="button"
                    onClick={() => selectPersona(p.key)}
                    className={`flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${
                      on ? 'border-primary bg-primary-subtle text-text' : 'border-border bg-bg/70 text-text-secondary hover:border-primary'
                    }`}
                  >
                    <span className="grid h-5 w-5 place-items-center rounded-full bg-primary text-[10px] text-white">
                      {p.name.charAt(0)}
                    </span>
                    {p.name} — {t(p.styleLabelId)}
                  </button>
                )
              })}
            </div>

            {/* The same node, rendered for the selected learner */}
            <AnimatePresence mode="wait" initial={false}>
              <motion.div key={persona} {...fade}>
                <UiSpecRenderer program={activeProgram} nodeId={`scene-${persona}`} />
                <p className="mt-3 flex items-center gap-1.5 text-xs text-primary">
                  <span aria-hidden>✦</span>
                  {t(persona === 'ana' ? 'adminScene.adaptNote.ana' : 'adminScene.adaptNote.bruno')}
                </p>
              </motion.div>
            </AnimatePresence>

            {beat >= 2 && !metricsLive && (
              <div className="mt-4 flex justify-end">
                <Button variant="primary" onClick={revealPanel}>
                  {t('adminScene.seePanel')}
                </Button>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Metrics — come alive on beat 3 */}
      {metricsLive && (
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <AnimatedMetric label={t('adminScene.metric.employees')} icon={<UsersIcon />} target={SCENE_DEMO_STATS.active_employees} suffix={`/${SCENE_DEMO_STATS.total_employees}`} run={metricsLive} reduce={reduce} />
          <AnimatedMetric label={t('adminScene.metric.courses')} icon={<BookIcon />} target={SCENE_DEMO_STATS.published_courses} run={metricsLive} reduce={reduce} />
          <AnimatedMetric label={t('adminScene.metric.enrollments')} icon={<TargetIcon />} target={SCENE_DEMO_STATS.total_enrollments} run={metricsLive} reduce={reduce} />
          <AnimatedMetric label={t('adminScene.metric.score')} icon={<ChartIcon />} target={Math.round((SCENE_DEMO_STATS.avg_score ?? 0) * 100)} suffix="%" run={metricsLive} reduce={reduce} />
        </div>
      )}

      {/* Hand-off */}
      {beat >= 3 && (
        <motion.div
          initial={reduce ? false : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={reduce ? { duration: 0 } : { duration: duration.normal, ease: ease.base }}
          className="mt-4 flex flex-col gap-3 rounded-xl border border-primary/40 bg-gradient-to-r from-primary/15 to-success/10 p-4 sm:flex-row sm:items-center"
        >
          <div className="flex-1">
            <p className="font-medium text-text">{t('adminScene.cta.title')}</p>
            <p className="mt-0.5 text-sm text-text-secondary">{t('adminScene.cta.body')}</p>
          </div>
          <div className="flex gap-3">
            <Button variant="ghost" onClick={onDismiss}>{t('adminScene.cta.clean')}</Button>
            <Button variant="primary" onClick={() => navigate('/admin/crear-curso')}>{t('adminScene.cta.create')}</Button>
          </div>
        </motion.div>
      )}
    </div>
  )
}
