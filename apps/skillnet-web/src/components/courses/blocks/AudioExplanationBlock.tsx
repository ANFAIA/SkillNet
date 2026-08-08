import { useCallback, useEffect, useRef, useState } from 'react'
import { useIntl } from 'react-intl'
import { AnimatePresence, motion } from 'framer-motion'
import { duration, ease } from '../../../lib/motion'
import { INLINE_SURFACE } from './rhythm'

export interface AudioExplanationBlockProps {
  text: string
  voice: 'neutral' | 'warm' | 'formal'
}

type PlayState = 'idle' | 'loading' | 'playing' | 'paused'

const BASE = '/api/v1'

export function AudioExplanationBlock({ text, voice }: AudioExplanationBlockProps) {
  const intl = useIntl()
  const safeText = typeof text === 'string' ? text : ''
  const words = safeText.split(/\s+/).filter(Boolean)

  const [state, setState] = useState<PlayState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [highlightIndex, setHighlightIndex] = useState(-1)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const blobRef = useRef<Blob | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const startTimeRef = useRef(0)
  const pausedAtRef = useRef(0)

  const clearHighlightInterval = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  // Estimate total duration from text length: ~80ms per character is a rough
  // approximation for Spanish TTS at normal speed.
  const estimatedDuration = Math.max(1, safeText.length * 0.08)

  const startHighlighting = useCallback(
    (offset: number) => {
      if (words.length === 0) return
      const msPerWord = (estimatedDuration * 1000) / words.length
      startTimeRef.current = Date.now() - offset
      clearHighlightInterval()
      intervalRef.current = setInterval(() => {
        const elapsed = Date.now() - startTimeRef.current
        const idx = Math.floor(elapsed / msPerWord)
        if (idx >= words.length) {
          setHighlightIndex(-1)
          clearHighlightInterval()
          return
        }
        setHighlightIndex(idx)
      }, 50)
    },
    [words.length, estimatedDuration, clearHighlightInterval],
  )

  const fetchAndPlay = useCallback(async () => {
    setState('loading')
    setError(null)
    setHighlightIndex(-1)

    try {
      let blob = blobRef.current
      if (!blob) {
        const res = await fetch(`${BASE}/tts/synthesize`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: safeText, voice: voice ?? 'default', language: 'es' }),
        })
        if (!res.ok) throw new Error('TTS request failed')
        blob = await res.blob()
        blobRef.current = blob
      }

      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audioRef.current = audio

      audio.addEventListener('ended', () => {
        setState('idle')
        setHighlightIndex(-1)
        clearHighlightInterval()
        URL.revokeObjectURL(url)
      })

      audio.addEventListener('error', () => {
        setState('idle')
        setError(intl.formatMessage({ id: 'audio.unavailable' }))
        clearHighlightInterval()
        URL.revokeObjectURL(url)
      })

      await audio.play()
      setState('playing')
      pausedAtRef.current = 0
      startHighlighting(0)
    } catch {
      setState('idle')
      setError(intl.formatMessage({ id: 'audio.unavailable' }))
    }
  }, [safeText, voice, startHighlighting, clearHighlightInterval, intl])

  const handlePlayPause = useCallback(() => {
    if (state === 'idle' || state === 'loading') {
      fetchAndPlay()
      return
    }
    if (state === 'playing' && audioRef.current) {
      audioRef.current.pause()
      pausedAtRef.current = Date.now() - startTimeRef.current
      clearHighlightInterval()
      setState('paused')
      return
    }
    if (state === 'paused' && audioRef.current) {
      audioRef.current.play()
      setState('playing')
      startHighlighting(pausedAtRef.current)
    }
  }, [state, fetchAndPlay, clearHighlightInterval, startHighlighting])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearHighlightInterval()
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current = null
      }
    }
  }, [clearHighlightInterval])

  const buttonLabel =
    state === 'loading'
      ? intl.formatMessage({ id: 'audio.loading' })
      : state === 'playing'
        ? intl.formatMessage({ id: 'audio.pause' })
        : state === 'paused'
          ? intl.formatMessage({ id: 'audio.resume' })
          : intl.formatMessage({ id: 'audio.listen' })

  return (
    <div data-no-explain="" className={`${INLINE_SURFACE} bg-bg-subtle`}>
      {/* Play/pause button */}
      <div className="flex items-center gap-3 mb-3">
        <motion.button
          type="button"
          onClick={handlePlayPause}
          disabled={state === 'loading'}
          className="inline-flex items-center gap-2 text-xs font-medium px-3 py-1.5 rounded-lg bg-primary text-white disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          whileHover={state === 'loading' ? undefined : { scale: 1.02 }}
          whileTap={state === 'loading' ? undefined : { scale: 0.97 }}
        >
          {/* Icon: play, pause, or spinner */}
          {state === 'loading' ? (
            <svg
              className="animate-spin h-3.5 w-3.5"
              viewBox="0 0 24 24"
              fill="none"
              aria-hidden="true"
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : state === 'playing' ? (
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <rect x="6" y="4" width="4" height="16" rx="1" />
              <rect x="14" y="4" width="4" height="16" rx="1" />
            </svg>
          ) : (
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M8 5v14l11-7z" />
            </svg>
          )}
          {buttonLabel}
        </motion.button>

        {voice && (
          <span className="text-xs text-text-muted">
            {intl.formatMessage({ id: 'audio.voice' }, { voice })}
          </span>
        )}
      </div>

      {/* Text with word highlighting */}
      <p className="text-sm leading-relaxed text-text">
        {words.map((word, i) => (
          <span
            key={i}
            className={
              i === highlightIndex
                ? 'bg-primary/20 text-primary rounded px-0.5 transition-colors duration-100'
                : 'transition-colors duration-100'
            }
          >
            {word}{i < words.length - 1 ? ' ' : ''}
          </span>
        ))}
      </p>

      {/* Error message */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: duration.fast, ease: ease.base }}
            className="mt-3 text-xs text-danger"
            role="alert"
          >
            {error}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
