import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { useIntl } from 'react-intl'
import { Mascota } from './Mascota'
import type { MascotaAnim } from './Mascota'
import { useReducedMotion } from '../../hooks/useReducedMotion'
import { usePreferences } from '../../stores/preferences'
import { screenReadText } from './screenReadText'

/**
 * The mascot as a proactive companion (inspired by Brilliant's "Koji").
 *
 * On entering a node a minimal bubble always shows the very text the mascot
 * "says" (the node's opening) — muted or not, the companion still speaks in
 * text. A single SVG speaker icon tucked into the bubble's top-right corner
 * controls only the audio: unmuted it shows a normal speaker and auto-reads the
 * text aloud through the TTS endpoint (`POST /api/v1/tts/synthesize`, cached
 * server-side, no click needed); muted it shows a slashed speaker and plays
 * nothing, but the text and bubble stay. Clicking it mutes — stopping any
 * playback at once and suppressing the auto-read on later nodes — and clicking
 * again un-mutes and reads the current node. The muted state is persisted
 * (`mascotaMuted`); default is not muted.
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
/** Let the node settle before the auto-read begins — a greeting, not a pop-up. */
const READ_DELAY_MS = 650

export interface MascotaCompanionProps {
  /** Changes per node; drives the per-node auto-read reset. */
  nodeId: string
  /** Node title — the fallback read text when the node has no summary. */
  title: string
  /** Node summary — the fallback read-aloud source when there is no per-screen text. */
  summary: string | null
  /**
   * The lesson program (OpenUI Lang text) of a paginated episode, or `null` in the
   * legacy shell. When present, the mascot reads the CURRENT screen's own text
   * instead of the whole-node summary — the companion speaks per page.
   */
  program?: string | null
  /**
   * Index of the screen the learner is on within a paginated episode. Drives the
   * per-screen read text and re-read; ignored (stays `0`) in the legacy shell.
   */
  screen?: number
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

export function MascotaCompanion({ nodeId, title, summary, program = null, screen = 0, fx, onOpenChat }: MascotaCompanionProps) {
  const intl = useIntl()
  const reduceMotion = useReducedMotion()
  const locale = usePreferences((s) => s.locale)
  const muted = usePreferences((s) => s.mascotaMuted)
  const setMascotaMuted = usePreferences((s) => s.setMascotaMuted)

  const [playing, setPlaying] = useState(false)

  // Per page: the current screen's own text when this is a paginated episode, and the
  // whole-node summary only as a fallback (legacy shell, or a screen with no prose).
  const readText = useMemo(() => {
    const perScreen = screenReadText(program, screen)
    return readableLead(perScreen ?? summary, title)
  }, [program, screen, summary, title])

  // One read per screen: the cache and the auto-read reset are keyed by node AND screen,
  // so paging forward speaks the new page and each page's audio is cached on its own.
  const readKey = `${nodeId}:${screen}`

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
    setPlaying(false)
  }, [])

  const speak = useCallback(async () => {
    stop()
    try {
      let blob = blobCacheRef.current.get(readKey)
      if (!blob) {
        const res = await fetch(`${BASE}/tts/synthesize`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: readText, voice: 'warm', language: locale }),
        })
        if (!res.ok) throw new Error('TTS request failed')
        blob = await res.blob()
        blobCacheRef.current.set(readKey, blob)
      }

      const url = URL.createObjectURL(blob)
      objectUrlRef.current = url
      const audio = new Audio(url)
      audioRef.current = audio
      audio.addEventListener('ended', stop)
      audio.addEventListener('error', stop)
      await audio.play()
      setPlaying(true)
    } catch {
      // A blocked autoplay throws too; stay silent, no error nag.
      setPlaying(false)
      throw new Error('speak failed')
    }
  }, [readKey, readText, locale, stop])

  // The speaker icon is a mute toggle. Muting stops playback at once and blocks
  // the auto-read on later nodes; un-muting is a user gesture, so we read the
  // current node's opening right away (best-effort, no nag).
  const handleToggleMute = useCallback(() => {
    const next = !muted
    setMascotaMuted(next)
    if (next) {
      stop()
    } else {
      void speak().catch(() => undefined)
    }
  }, [muted, setMascotaMuted, stop, speak])

  // Per-screen auto-read: stop the previous screen's audio, then read this page's
  // text after a short beat unless muted — silently, since a blocked play()
  // (autoplay policy) must not nag. Re-runs whenever the node OR the screen changes,
  // so advancing a page speaks the new page.
  useEffect(() => {
    stop()
    const timer = window.setTimeout(() => {
      if (!muted) void speak().catch(() => undefined)
    }, READ_DELAY_MS)
    return () => window.clearTimeout(timer)
    // `speak`/`stop` are stable per (node, screen); re-running only when the page
    // changes is the intent (one read per page). `muted` is read fresh inside.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readKey])

  // Stop any audio when the companion leaves the screen.
  useEffect(() => stop, [stop])

  const anim: MascotaAnim = fx ?? (playing ? 'talk' : 'idle')

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

      {/* The bubble with what the mascot "says" is always shown. The speaker in
          its top-right corner controls only the audio: mute silences the read
          (icon slashed) but the text stays; un-muting reads the current node. */}
      <div className="relative mb-1 max-w-[210px] md:max-w-[260px] rounded-2xl rounded-bl-sm border border-border bg-bg shadow-sm px-3 py-2">
        <p className="pr-6 text-xs leading-relaxed text-text" role="status">
          {readText}
        </p>
        <button
          type="button"
          onClick={handleToggleMute}
          aria-pressed={muted}
          aria-label={intl.formatMessage({ id: muted ? 'mascota.unmute' : 'mascota.mute' })}
          className={`absolute top-1 right-1 inline-flex h-7 w-7 items-center justify-center rounded-full transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:ring-offset-1 ${
            muted ? 'text-text-muted hover:text-text' : 'text-primary hover:text-primary/80'
          }`}
        >
          {muted ? (
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
        </button>
      </div>
    </div>
  )
}

export default MascotaCompanion
