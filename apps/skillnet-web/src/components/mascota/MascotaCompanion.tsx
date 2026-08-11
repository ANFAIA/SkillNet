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
 *  1. shows a short, contextual speech bubble that names the node, and
 *  2. auto-reads the node's opening sentence aloud through the TTS endpoint
 *     (`POST /api/v1/tts/synthesize`, cached server-side) — no click needed.
 *
 * Read-aloud is on by default. A single speaker button in the bubble is the
 * mute toggle: a normal speaker icon while reading, a slashed speaker when
 * muted. Clicking it mutes — stopping any playback at once and suppressing the
 * auto-read on later nodes — and clicking again un-mutes. The muted state is
 * persisted (`mascotaMuted` in the preferences store).
 *
 * Browser autoplay policy: `audio.play()` may reject before any user gesture,
 * so the very first node can stay silent. We attempt the read best-effort and
 * swallow the rejection (no error nag); it succeeds on the next node once any
 * gesture has happened, and un-muting is itself a gesture that reads right away.
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
  const muted = usePreferences((s) => s.mascotaMuted)
  const setMascotaMuted = usePreferences((s) => s.setMascotaMuted)

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

  // The speaker button is a mute toggle. Muting stops playback at once and
  // blocks the auto-read on later nodes; un-muting is a user gesture, so we
  // read the current node's opening right away (best-effort, no nag).
  const handleToggleMute = useCallback(() => {
    const next = !muted
    setMascotaMuted(next)
    if (next) {
      stop()
    } else {
      setError(false)
      void speak().catch(() => undefined)
    }
  }, [muted, setMascotaMuted, stop, speak])

  // Per-node greeting: reset, then show the bubble after a short beat and, unless
  // muted, auto-read the opening on the same beat — silently, since a blocked
  // play() (autoplay policy) must not nag.
  useEffect(() => {
    setBubbleVisible(false)
    setError(false)
    stop()
    const timer = window.setTimeout(() => {
      setBubbleVisible(true)
      if (!muted) void speak().catch(() => undefined)
    }, GREETING_DELAY_MS)
    return () => window.clearTimeout(timer)
    // `speak`/`stop` are stable per node; re-running only when the node changes
    // is the intent (one greeting per node). `muted` is read fresh inside.
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
              {/* Speaker = mute toggle. Icon reflects state; a spinner shows
                  while the (unmuted) read is being fetched. */}
              <button
                type="button"
                onClick={handleToggleMute}
                aria-pressed={muted}
                aria-label={intl.formatMessage({ id: muted ? 'mascota.unmute' : 'mascota.mute' })}
                className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-lg cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-1 ${
                  muted
                    ? 'border border-border text-text-muted hover:text-text'
                    : 'bg-primary text-white'
                }`}
              >
                {!muted && play === 'loading' ? (
                  <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : muted ? (
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                    <line x1="23" y1="9" x2="17" y2="15" /><line x1="17" y1="9" x2="23" y2="15" />
                  </svg>
                ) : (
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
                    <path d="M15.54 8.46a5 5 0 0 1 0 7.07" /><path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
                  </svg>
                )}
                <span>
                  {!muted && play === 'loading'
                    ? intl.formatMessage({ id: 'mascota.reading' })
                    : intl.formatMessage({ id: 'mascota.readAloudToggle' })}
                </span>
              </button>
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
