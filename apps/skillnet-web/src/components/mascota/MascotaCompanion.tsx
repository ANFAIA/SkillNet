import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useIntl } from 'react-intl'
import { Mascota } from './Mascota'
import type { MascotaAnim } from './Mascota'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { duration, ease } from '../../lib/motion'
import { usePreferences } from '../../stores/preferences'

/**
 * The mascot as a proactive companion (inspired by Brilliant's "Koji").
 *
 * On entering a node it does two things without being asked:
 *  1. shows a short, contextual speech bubble that names the node and offers to
 *     read its opening aloud, and
 *  2. exposes a "🔊 Escuchar" affordance that plays the node's first sentence
 *     through the TTS endpoint (`POST /api/v1/tts/synthesize`, cached server-side).
 *
 * Audio never autoplays on load — browsers block it and it is intrusive. The
 * mascot auto-*shows* the message; the sound only plays on the learner's click.
 * The one exception is the persisted "leer en voz" preference: once the learner
 * has enabled it (itself a user gesture), the following nodes read on entry, and
 * a blocked `play()` fails silently rather than nagging.
 *
 * Feedback reactions still win: `fx` (celebrar / ups, reported by an exercise)
 * overrides the talking animation so the existing celebrate/oops behaviour is
 * untouched.
 */

const BASE = '/api/v1'
/** TTS is short-form here: one or two sentences. Keep the request tiny. */
const MAX_READ_CHARS = 240
/** Let the node settle before the bubble arrives — a greeting, not a pop-up. */
const GREETING_DELAY_MS = 650

export interface MascotaCompanionProps {
  /** Changes per node; drives the per-node greeting reset. */
  nodeId: string
  /** Node title — woven into the contextual greeting. */
  title: string
  /** Node summary — the grounded source for the read-aloud (its own text). */
  summary: string | null
  /** Feedback reaction reported by a block; overrides the talking animation. */
  fx: 'celebrar' | 'ups' | null
  /** Open the tutor chat panel (the mascot button keeps its original job). */
  onOpenChat: () => void
}

/**
 * The node's own opening, grounded in its summary. We never invent facts: the
 * read text is the first sentence of the summary (capped), or the title when the
 * node has no summary at all.
 */
function readableLead(summary: string | null | undefined, title: string): string {
  const src = (summary ?? '').trim()
  if (!src) return title
  const match = src.match(/^[\s\S]*?[.!?](\s|$)/)
  const first = (match ? match[0] : src).trim()
  return first.length > MAX_READ_CHARS ? `${first.slice(0, MAX_READ_CHARS).trim()}…` : first
}

type PlayState = 'idle' | 'loading' | 'playing'

export function MascotaCompanion({ nodeId, title, summary, fx, onOpenChat }: MascotaCompanionProps) {
  const intl = useIntl()
  const reduceMotion = useReducedMotion()
  const locale = usePreferences((s) => s.locale)
  const readAloud = usePreferences((s) => s.readAloud)
  const setReadAloud = usePreferences((s) => s.setReadAloud)

  const [bubbleVisible, setBubbleVisible] = useState(false)
  const [play, setPlay] = useState<PlayState>('idle')
  const [error, setError] = useState(false)

  const readText = useMemo(() => readableLead(summary, title), [summary, title])

  // Audio plumbing. Blobs are cached per node so replaying (or re-reading on a
  // return visit) never hits the provider twice from the client either.
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const objectUrlRef = useRef<string | null>(null)
  const blobCacheRef = useRef<Map<string, Blob>>(new Map())

  const stop = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.src = ''
      audioRef.current = null
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current)
      objectUrlRef.current = null
    }
    setPlay('idle')
  }, [])

  const speak = useCallback(async () => {
    setError(false)
    stop()
    setPlay('loading')
    try {
      let blob = blobCacheRef.current.get(nodeId)
      if (!blob) {
        const res = await fetch(`${BASE}/tts/synthesize`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: readText, voice: 'warm', language: locale }),
        })
        if (!res.ok) throw new Error('TTS request failed')
        blob = await res.blob()
        blobCacheRef.current.set(nodeId, blob)
      }

      const url = URL.createObjectURL(blob)
      objectUrlRef.current = url
      const audio = new Audio(url)
      audioRef.current = audio
      audio.addEventListener('ended', stop)
      audio.addEventListener('error', () => {
        setError(true)
        stop()
      })
      await audio.play()
      setPlay('playing')
    } catch {
      // A blocked autoplay throws too; only surface a message for a real click.
      setPlay('idle')
      throw new Error('speak failed')
    }
  }, [nodeId, readText, locale, stop])

  const handleListen = useCallback(() => {
    if (play === 'playing' || play === 'loading') {
      stop()
      return
    }
    void speak().catch(() => setError(true))
  }, [play, speak, stop])

  // Per-node greeting: reset, then show the bubble after a short beat. When the
  // learner has opted into read-aloud, kick off the reading on the same beat —
  // silently, since a blocked play() must not nag.
  useEffect(() => {
    setBubbleVisible(false)
    setError(false)
    stop()
    const timer = window.setTimeout(() => {
      setBubbleVisible(true)
      if (readAloud) void speak().catch(() => undefined)
    }, GREETING_DELAY_MS)
    return () => window.clearTimeout(timer)
    // `speak`/`stop` are stable per node; re-running only when the node changes
    // is the intent (one greeting per node).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeId])

  // Stop any audio when the companion leaves the screen.
  useEffect(() => stop, [stop])

  const speaking = play === 'playing'
  const anim: MascotaAnim = fx ?? (speaking ? 'talk' : 'idle')

  const bubbleMotion = reduceMotion
    ? { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } }
    : {
        initial: { opacity: 0, scale: 0.94, y: 6 },
        animate: { opacity: 1, scale: 1, y: 0 },
        exit: { opacity: 0, scale: 0.94, y: 6 },
      }

  return (
    <div className="flex items-end gap-2 md:gap-3" data-no-explain="">
      {/* Mascot — keeps its original job of opening the tutor chat. */}
      <motion.button
        type="button"
        onClick={onOpenChat}
        className="w-14 h-14 md:w-[72px] md:h-[72px] shrink-0 cursor-pointer"
        whileHover={reduceMotion ? undefined : { scale: 1.08, y: -2 }}
        whileTap={reduceMotion ? undefined : { scale: 0.95 }}
        transition={{ type: 'spring', stiffness: 400, damping: 20 }}
        aria-label={intl.formatMessage({ id: 'panel.chat' })}
      >
        <Mascota anim={anim} size="100%" followCursor />
      </motion.button>

      {/* Contextual bubble with the read-aloud affordance. */}
      <AnimatePresence>
        {bubbleVisible && (
          <motion.div
            key="bubble"
            {...bubbleMotion}
            transition={{ duration: duration.normal, ease: [...ease.base] }}
            className="mb-1 max-w-[210px] md:max-w-[260px] rounded-2xl rounded-bl-sm border border-border bg-bg shadow-sm px-3 py-2.5"
            role="status"
          >
            <div className="flex items-start gap-2">
              <p className="flex-1 text-xs leading-relaxed text-text">
                {intl.formatMessage({ id: 'mascota.greeting' }, { title })}
              </p>
              <button
                type="button"
                onClick={() => setBubbleVisible(false)}
                className="shrink-0 -mr-1 -mt-0.5 p-1 text-text-muted hover:text-text transition-colors leading-none"
                aria-label={intl.formatMessage({ id: 'mascota.dismiss' })}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden="true">
                  <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>

            <div className="mt-2 flex items-center gap-2">
              <button
                type="button"
                onClick={handleListen}
                className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-lg bg-primary text-white disabled:opacity-60 cursor-pointer"
                aria-label={
                  speaking || play === 'loading'
                    ? intl.formatMessage({ id: 'mascota.stop' })
                    : intl.formatMessage({ id: 'mascota.listen' })
                }
              >
                {play === 'loading' ? (
                  <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : speaking ? (
                  <svg className="h-3 w-3" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <rect x="6" y="4" width="4" height="16" rx="1" /><rect x="14" y="4" width="4" height="16" rx="1" />
                  </svg>
                ) : (
                  <span aria-hidden="true">🔊</span>
                )}
                <span>
                  {play === 'loading'
                    ? intl.formatMessage({ id: 'mascota.reading' })
                    : speaking
                      ? intl.formatMessage({ id: 'mascota.stop' })
                      : intl.formatMessage({ id: 'mascota.listen' })}
                </span>
              </button>

              {/* Opt-in: once enabled (a gesture), later nodes read on entry. */}
              <label className="inline-flex items-center gap-1 text-[11px] text-text-muted cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={readAloud}
                  onChange={(e) => setReadAloud(e.target.checked)}
                  className="h-3 w-3 accent-[var(--color-primary)] cursor-pointer"
                />
                {intl.formatMessage({ id: 'mascota.readAloudToggle' })}
              </label>
            </div>

            {error && (
              <p className="mt-1.5 text-[11px] text-danger" role="alert">
                {intl.formatMessage({ id: 'mascota.unavailable' })}
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export default MascotaCompanion
