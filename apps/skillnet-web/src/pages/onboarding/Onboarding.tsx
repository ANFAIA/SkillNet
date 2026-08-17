import { useCallback, useMemo, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useIntl } from 'react-intl'
import { AnimatePresence, motion } from 'framer-motion'
import { Button, Card, StepIndicator } from '../../components/ui'
import { ShimmerSkeleton } from '../../components/ui/ShimmerSkeleton'
import { RoleStep } from '../../components/onboarding/RoleStep'
import { GoalStep } from '../../components/onboarding/GoalStep'
import { ExperienceStep } from '../../components/onboarding/ExperienceStep'
import { PresetStep } from '../../components/onboarding/PresetStep'
import { AccessibilityStep } from '../../components/onboarding/AccessibilityStep'
import { LearningPreferencesStep } from '../../components/onboarding/LearningPreferencesStep'
import { stepSlideVariants, transition } from '../../lib/motion'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { useAuth } from '../../hooks/useAuth'
import { ApiError } from '../../api/client'
import {
  NO_ACCESSIBILITY,
  useOnboardingQuestions,
  useSkipOnboarding,
  useSubmitOnboarding,
} from '../../api/onboarding'
import type {
  AccessibilityKey,
  AccessibilitySettings,
  ExperienceLevel,
  LearningPreset,
  ModalityPreference,
  OnboardingQuestion,
  OnboardingSubmitBody,
} from '../../api/onboarding'

// Where an answered, skipped or unavailable wizard sends the learner is computed
// per render from the user's home: an employee returns to /empleado; the owner of
// an `individual` deployment is an admin and returns to /admin. See
// `afterOnboarding` inside the component.

/**
 * Built once: the outgoing step leaves in 200 ms and the incoming one lands in 300,
 * instead of 300 each way. Five screens at `mode="wait"` made the symmetric version
 * cost 3 s of pure waiting out of the ≤90 s the wizard is allowed (§6.1) — and a wait
 * you sit through between questions is what makes five questions feel like ten.
 */
const stepSlide = stepSlideVariants(64)

/**
 * The question ids this wizard knows how to render, in the order of §6.2. A
 * question the client does not understand is dropped rather than rendered blank,
 * and the step count follows the questions that survive — so the indicator never
 * promises a screen that does not exist.
 */
const KNOWN_STEP_IDS: readonly string[] = [
  'role_title',
  'goal',
  'experience_level',
  'preset',
  'learning_preferences',
  'accessibility',
]

/** Wizard chrome, shared by the loading, error and answering states. */
function Shell({ children, indicator }: { children: ReactNode; indicator?: ReactNode }) {
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card className="w-full max-w-lg bg-surface">
        <div className="flex items-center justify-between gap-4 mb-6">
          <img src="/logo.png" alt="SkillNet" className="w-8 h-8" />
          {indicator}
        </div>
        {children}
      </Card>
    </div>
  )
}

/** Question-shaped placeholder: prompt line plus three option rows (§9.2). */
function LoadingShell() {
  return (
    <Shell>
      <ShimmerSkeleton className="h-5 w-2/3" />
      <div className="mt-4 space-y-2">
        <ShimmerSkeleton className="h-11 w-full" />
        <ShimmerSkeleton className="h-11 w-full" />
        <ShimmerSkeleton className="h-11 w-full" />
      </div>
    </Shell>
  )
}

/**
 * Onboarding wizard — one server-provided question per screen, at most 3 visible
 * elements, target ≤90 seconds, skippable at any moment (§6.1).
 *
 * The limits are not stylistic: they come from the documented attention
 * adaptations (tests of at most 5 questions, 3 bullets per screen). Every screen
 * here is therefore question + control + navigation, and nothing else. Screen 1
 * additionally carries the art. 13 notice, which §3.3 requires at the point of
 * collection.
 *
 * Mounted **outside** `AppLayout`: a learner who has not answered yet has no
 * sidebar to navigate with, and the gate in `ProtectedRoute` would fight the
 * layout for the first paint.
 *
 * "Lo hago luego" calls `POST /onboarding/skip`, which writes
 * `experience_level = 'unknown'`. It does **not** submit `'none'`: `'none'` means
 * "declares being a novice" and forces novice scaffolding, which is exactly the
 * case that hurts the expert (§6.1). Whoever skips has declared nothing, and a
 * partial submit behaves the same way — the field is simply absent from the body.
 */
export function Onboarding() {
  const navigate = useNavigate()
  const intl = useIntl()
  const reduceMotion = useReducedMotion()
  const { user } = useAuth()
  // The owner of an `individual` deployment is an admin who also learns, so the
  // wizard returns them to /admin, not the learner home. See audience-modes.md.
  const afterOnboarding = user?.role === 'admin' ? '/admin' : '/empleado'

  const questionsQuery = useOnboardingQuestions()
  const submit = useSubmitOnboarding()
  const skip = useSkipOnboarding()

  const [step, setStep] = useState(0)
  const [direction, setDirection] = useState<1 | -1>(1)

  const [roleTitle, setRoleTitle] = useState('')
  const [goal, setGoal] = useState('')
  const [experience, setExperience] = useState<ExperienceLevel | null>(null)
  const [preset, setPreset] = useState<LearningPreset | null>(null)
  const [modality, setModality] = useState<ModalityPreference | null>(null)
  const [accessibility, setAccessibility] = useState<AccessibilitySettings>(NO_ACCESSIBILITY)

  const questions = useMemo(
    () => (questionsQuery.data?.questions ?? []).filter((q) => KNOWN_STEP_IDS.includes(q.id)),
    [questionsQuery.data],
  )

  /**
   * Focus moves to the new question as it mounts. A callback ref, not an effect:
   * with `AnimatePresence mode="wait"` the incoming step is not in the DOM yet
   * when a `[step]` effect would run.
   */
  const focusStep = useCallback((node: HTMLDivElement | null) => {
    node?.focus()
  }, [])

  const total = questions.length
  const currentQuestion: OnboardingQuestion | undefined = questions[step]
  const isLastStep = step === total - 1

  const pending = submit.isPending || skip.isPending

  function isAnswered(question: OnboardingQuestion): boolean {
    switch (question.id) {
      case 'role_title':
        return roleTitle.trim().length > 0
      case 'goal':
        return goal.trim().length > 0
      case 'experience_level':
        return experience !== null
      case 'preset':
        return preset !== null
      case 'learning_preferences':
        return true
      default:
        // Question 5 is optional (`optional: true`): no reading setting is a
        // complete answer.
        return true
    }
  }

  /**
   * Only what the learner actually declared. An unanswered field is **absent**,
   * never a default — the server turns an absent `experience_level` into
   * `'unknown'`, and that mapping must stay in one place (§6.1).
   */
  function buildBody(): OnboardingSubmitBody {
    const body: OnboardingSubmitBody = {}
    const role = roleTitle.trim()
    const declaredGoal = goal.trim()
    if (role) body.role_title = role
    if (declaredGoal) body.goal = declaredGoal
    if (experience) body.experience_level = experience
    if (preset) body.preset = preset
    if (modality) {
      body.learning_preferences = {
        version: 3,
        web_presentation:
          modality === 'text' || modality === 'visual' || modality === 'data'
            ? modality
            : 'balanced',
        modalities: modality === 'audio' ? ['audio'] : [],
        interaction: 'standard',
        detail: 'standard',
        images: 'when_useful',
      }
    }
    body.accessibility = accessibility
    return body
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (pending || !currentQuestion || !isAnswered(currentQuestion)) return

    if (!isLastStep) {
      setDirection(1)
      setStep(step + 1)
      return
    }

    submit.mutate(buildBody(), {
      onSuccess: () => navigate(afterOnboarding, { replace: true }),
    })
  }

  function handleBack() {
    if (step === 0 || pending) return
    setDirection(-1)
    setStep(step - 1)
  }

  function handleSkip() {
    if (pending) return
    skip.mutate(undefined, {
      onSuccess: () => navigate(afterOnboarding, { replace: true }),
    })
  }

  function toggleAccessibility(key: AccessibilityKey, enabled: boolean) {
    setAccessibility((previous) => ({ ...previous, [key]: enabled }))
  }

  if (questionsQuery.isLoading) return <LoadingShell />

  if (questionsQuery.isError) {
    // A 404 means the flag went off mid-session: leave, do not retry a route that
    // no longer exists.
    if (questionsQuery.error instanceof ApiError && questionsQuery.error.status === 404) {
      return <Navigate to={afterOnboarding} replace />
    }
    return (
      <Shell>
        <p className="text-sm text-text">{intl.formatMessage({ id: 'onboarding.loadError' })}</p>
        <div className="flex items-center gap-2 mt-4">
          <Button variant="secondary" onClick={() => questionsQuery.refetch()}>
            {intl.formatMessage({ id: 'onboarding.retry' })}
          </Button>
          <Button variant="ghost" onClick={() => navigate(afterOnboarding, { replace: true })}>
            {intl.formatMessage({ id: 'onboarding.skipForNow' })}
          </Button>
        </div>
      </Shell>
    )
  }

  if (!currentQuestion || total === 0) return <Navigate to={afterOnboarding} replace />

  const notice = questionsQuery.data?.notice ?? ''

  function renderQuestion(question: OnboardingQuestion) {
    switch (question.id) {
      case 'role_title':
        return (
          <RoleStep
            question={question}
            notice={notice}
            value={roleTitle}
            onChange={setRoleTitle}
          />
        )
      case 'goal':
        return <GoalStep question={question} value={goal} onChange={setGoal} />
      case 'experience_level':
        return (
          <ExperienceStep question={question} value={experience} onChange={setExperience} />
        )
      case 'preset':
        return <PresetStep question={question} value={preset} onChange={setPreset} />
      case 'learning_preferences':
        return (
          <LearningPreferencesStep
            question={question}
            value={modality}
            onChange={setModality}
          />
        )
      case 'accessibility':
        return (
          <AccessibilityStep
            question={question}
            value={accessibility}
            onToggle={toggleAccessibility}
          />
        )
      default:
        return null
    }
  }

  const stepBody = (
    <>
      <h1 className="sr-only">{intl.formatMessage({ id: 'onboarding.srTitle' })}</h1>
      {renderQuestion(currentQuestion)}
    </>
  )

  return (
    <Shell
      indicator={
        <>
          {/* The indicator renders digits, which read as "1 2 3 4 5" out loud. */}
          <div aria-hidden="true">
            <StepIndicator current={step} total={total} />
          </div>
          <p role="status" className="sr-only">
            {intl.formatMessage({ id: 'onboarding.stepOf' }, { current: step + 1, total })}
          </p>
        </>
      }
    >
      <form onSubmit={handleSubmit} noValidate>
        {/* One panel that resizes, not five screens of different heights. A question
            with four options is taller than one with a text field, and with the height
            snapping between steps the card read as a new page every time — which is
            the single thing that made a 5-question wizard feel long. `layout` lets the
            card settle instead; the step inside is a `motion.div`, so framer's scale
            correction keeps the text undistorted while it does.

            Dropped entirely under reduced motion, where the plain swap below is the
            accessible degradation: no travel, no fade, no resize. */}
        <motion.div
          className="overflow-hidden"
          layout={reduceMotion ? false : 'size'}
          transition={transition.resize}
        >
          <AnimatePresence mode="wait" custom={direction} initial={false}>
            {reduceMotion ? (
              <div key={step} ref={focusStep} tabIndex={-1} data-step={currentQuestion.id}>
                {stepBody}
              </div>
            ) : (
              <motion.div
                key={step}
                ref={focusStep}
                tabIndex={-1}
                data-step={currentQuestion.id}
                custom={direction}
                variants={stepSlide}
                initial="enter"
                animate="center"
                exit="exit"
              >
                {stepBody}
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>

        {submit.isError && (
          <p className="text-sm text-danger mt-4">
            {submit.error instanceof ApiError
              ? submit.error.body.detail
              : intl.formatMessage({ id: 'onboarding.submitError' })}
          </p>
        )}
        {skip.isError && (
          <p className="text-sm text-danger mt-4">
            {intl.formatMessage({ id: 'onboarding.skipError' })}
          </p>
        )}

        <div className="flex items-center justify-between gap-3 mt-8 pt-4 border-t border-border">
          <div>
            {step > 0 && (
              <Button type="button" variant="secondary" onClick={handleBack} disabled={pending}>
                {intl.formatMessage({ id: 'onboarding.back' })}
              </Button>
            )}
          </div>
          <Button type="submit" variant="primary" disabled={pending || !isAnswered(currentQuestion)}>
            {isLastStep ? (submit.isPending ? intl.formatMessage({ id: 'onboarding.saving' }) : intl.formatMessage({ id: 'onboarding.finish' })) : intl.formatMessage({ id: 'onboarding.continue' })}
          </Button>
        </div>

        <div className="flex justify-center mt-3">
          <Button type="button" variant="ghost" size="sm" onClick={handleSkip} disabled={pending}>
            {intl.formatMessage({ id: 'onboarding.skipForNow' })}
          </Button>
        </div>
      </form>
    </Shell>
  )
}
