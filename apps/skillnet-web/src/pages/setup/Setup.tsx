import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useIntl } from 'react-intl'
import { motion, AnimatePresence, LayoutGroup } from 'framer-motion'
import { Button, Input, Logo } from '../../components/ui'
import { Mascota } from '../../features/mascot'
import { ApiError } from '../../api/client'
import { useSubmitSetup } from '../../api/setup'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { duration, ease, spring } from '../../lib/motion'
import type { WorkspaceMode } from '../../types'

type Stage = 'welcome' | 'choose'

// Local morph consts, mirroring CreateCourse: the container box springs to its
// new size (layoutId), and the inner content fades in only once it settles.
// Opacity only — no blur, and the text is never scaled (it is a child that fades).
const morphTransition = { type: 'spring' as const, stiffness: 200, damping: 28 }
const innerFadeIn = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: duration.normal, ease: ease.base, delay: 0.35 } },
}
const innerFadeOut = { exit: { opacity: 0, transition: { duration: duration.fast, ease: ease.base } } }

const MODES: { key: WorkspaceMode; titleId: string; descId: string }[] = [
  { key: 'organization', titleId: 'setup.mode.organization', descId: 'setup.mode.organizationDesc' },
  { key: 'individual', titleId: 'setup.mode.individual', descId: 'setup.mode.individualDesc' },
]

/**
 * First-boot wizard. Shown only while the deployment has no owner (App gates it
 * on `/setup/status`). Two mode cards; the chosen one morphs open to reveal the
 * owner form. On success the owner is signed in and sent onward. Full-screen,
 * outside AppLayout — there is no session yet. See docs/design/audience-modes.md.
 */
export function Setup() {
  const intl = useIntl()
  const navigate = useNavigate()
  const reduce = useReducedMotion()
  const submit = useSubmitSetup()

  const [stage, setStage] = useState<Stage>('welcome')
  const [mode, setMode] = useState<WorkspaceMode | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [orgName, setOrgName] = useState('')
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const isOrg = mode === 'organization'
  const canSubmit =
    fullName.trim().length > 0 &&
    email.trim().length > 0 &&
    password.length >= 8 &&
    (!isOrg || orgName.trim().length > 0)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!mode || !canSubmit) return
    try {
      await submit.mutateAsync({
        workspace_mode: mode,
        org_name: isOrg ? orgName.trim() : undefined,
        owner_full_name: fullName.trim(),
        owner_email: email.trim(),
        owner_password: password,
      })
      // Auto-logged in. The owner also learns in individual mode, so send them to
      // the learner onboarding; an organization admin goes to their dashboard.
      navigate(mode === 'individual' ? '/onboarding' : '/admin', { replace: true })
    } catch {
      // Surfaced below via submit.error.
    }
  }

  const submitError = submit.error
  const errorText =
    submitError instanceof ApiError
      ? submitError.body.detail
      : submitError
        ? intl.formatMessage({ id: 'setup.submitError' })
        : null

  function ownerForm() {
    return (
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-text">
            {intl.formatMessage({ id: 'setup.ownerTitle' })}
          </h2>
          {isOrg && (
            <p className="mt-1 text-sm text-text-secondary">
              {intl.formatMessage({ id: 'setup.ownerSubtitleOrg' })}
            </p>
          )}
        </div>

        {isOrg && (
          <Input
            label={intl.formatMessage({ id: 'setup.orgName' })}
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            placeholder={intl.formatMessage({ id: 'setup.orgNamePlaceholder' })}
            autoComplete="organization"
          />
        )}
        <Input
          label={intl.formatMessage({ id: 'setup.fullName' })}
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          autoComplete="name"
        />
        <Input
          label={intl.formatMessage({ id: 'setup.email' })}
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="username"
        />
        <div>
          <Input
            label={intl.formatMessage({ id: 'setup.password' })}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
          />
          <p className="mt-1 text-xs text-text-muted">
            {intl.formatMessage({ id: 'setup.passwordHint' })}
          </p>
        </div>

        {errorText && (
          <p className="text-sm text-danger" role="alert">
            {errorText}
          </p>
        )}

        <div className="flex items-center justify-between gap-3 pt-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() => setExpanded(false)}
            disabled={submit.isPending}
          >
            {intl.formatMessage({ id: 'setup.back' })}
          </Button>
          <Button type="submit" variant="primary" disabled={!canSubmit || submit.isPending}>
            {submit.isPending
              ? intl.formatMessage({ id: 'setup.creating' })
              : intl.formatMessage({ id: 'setup.create' })}
          </Button>
        </div>
      </form>
    )
  }

  // The existing mode → owner-form step, unchanged in behaviour: two mode cards,
  // the chosen one morphs open to reveal the owner form. Extracted so the new
  // welcome stage can sit in front of it.
  function modeChooser() {
    return (
      <LayoutGroup>
        <div className={expanded ? '' : 'grid grid-cols-1 sm:grid-cols-2 gap-4'}>
          {MODES.map(({ key, titleId, descId }) => {
            const active = mode === key
            // When expanded, only the chosen card stays mounted so its layoutId
            // morphs it to full width; the other unmounts.
            if (expanded && !active) return null
            return (
              <motion.div
                key={key}
                layoutId={reduce ? undefined : `mode-card-${key}`}
                transition={morphTransition}
                style={{ borderRadius: 8 }}
                onClick={() => {
                  if (!expanded) setMode(key)
                }}
                className={`border p-6 ${
                  expanded
                    ? 'border-primary bg-bg'
                    : active
                      ? 'border-primary bg-primary-subtle cursor-pointer'
                      : 'border-border bg-bg/70 hover:border-primary cursor-pointer'
                }`}
              >
                <AnimatePresence mode="wait" initial={false}>
                  {expanded && active ? (
                    <motion.div key="form" {...innerFadeIn} {...innerFadeOut}>
                      {ownerForm()}
                    </motion.div>
                  ) : (
                    <motion.div key="summary" {...innerFadeIn} {...innerFadeOut}>
                      <h2 className="text-base font-semibold text-text">
                        {intl.formatMessage({ id: titleId })}
                      </h2>
                      <p className="mt-1 text-sm text-text-secondary">
                        {intl.formatMessage({ id: descId })}
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            )
          })}
        </div>

        {!expanded && (
          <div className="mt-6 flex items-center justify-between gap-3">
            <Button variant="ghost" onClick={() => setStage('welcome')}>
              {'← '}
              {intl.formatMessage({ id: 'setup.previous' })}
            </Button>
            <Button variant="primary" disabled={!mode} onClick={() => setExpanded(true)}>
              {intl.formatMessage({ id: 'setup.continue' })}
            </Button>
          </div>
        )}
      </LayoutGroup>
    )
  }

  const stageFade = {
    initial: { opacity: 0, y: reduce ? 0 : 8 },
    animate: { opacity: 1, y: 0, transition: { duration: duration.normal, ease: ease.base } },
    exit: { opacity: 0, y: reduce ? 0 : -8, transition: { duration: duration.fast, ease: ease.base } },
  }

  return (
    <div className="setup-welcome-bg relative min-h-screen overflow-hidden flex flex-col items-center justify-center p-4">
      <div className="absolute top-6 left-1/2 -translate-x-1/2">
        <Logo size={30} tone="accent" />
      </div>

      <LayoutGroup>
        <motion.div layout={!reduce} className="w-full max-w-2xl flex flex-col items-center">
          {/* One continuous mascot: it repositions (layout) and scales down as we
              move from welcome to the mode choice, rather than unmounting. */}
          <motion.div
            layout={!reduce}
            animate={{ scale: stage === 'welcome' ? 1 : 0.62 }}
            transition={reduce ? { duration: 0 } : spring.gentle}
            className="origin-center"
          >
            <Mascota size={200} expression={stage === 'welcome' ? 'idle' : 'happy'} />
          </motion.div>

          <AnimatePresence mode="wait" initial={false}>
            {stage === 'welcome' ? (
              <motion.div
                key="welcome"
                {...stageFade}
                className="mt-6 flex flex-col items-center text-center"
              >
                <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-text">
                  {intl.formatMessage({ id: 'setup.welcomeTitle' })}
                </h1>
                <p className="mt-3 max-w-sm text-base text-text-secondary">
                  {intl.formatMessage({ id: 'setup.welcomeSubtitle' })}
                </p>
                <Button
                  variant="accent"
                  size="lg"
                  className="mt-8 rounded-full px-10 py-3 text-base shadow-sm"
                  onClick={() => setStage('choose')}
                >
                  {intl.formatMessage({ id: 'setup.start' })}
                </Button>
              </motion.div>
            ) : (
              <motion.div key="choose" {...stageFade} className="mt-6 w-full">
                <h2 className="mb-5 text-center text-lg font-semibold text-text">
                  {intl.formatMessage({ id: 'setup.chooseTitle' })}
                </h2>
                {modeChooser()}
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      </LayoutGroup>
    </div>
  )
}
