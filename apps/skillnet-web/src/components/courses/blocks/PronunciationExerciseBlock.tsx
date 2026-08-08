import { useCallback, useEffect, useRef, useState } from 'react'
import { useIntl } from 'react-intl'
import WaveSurfer from 'wavesurfer.js'
import { AnimatePresence, motion } from 'framer-motion'
import { Button } from '../../ui'
import { duration, ease } from '../../../lib/motion'
import { BLOCK_TITLE, INLINE_SURFACE } from './rhythm'

export interface PronunciationExerciseBlockProps {
  targetText: string
  language: string
}

type ExerciseState = 'idle' | 'listening' | 'recording' | 'comparing'

const BASE = '/api/v1'

function useWaveSurfer(containerRef: React.RefObject<HTMLDivElement | null>) {
  const wsRef = useRef<WaveSurfer | null>(null)

  const create = useCallback(() => {
    if (!containerRef.current) return null
    // Destroy previous instance
    if (wsRef.current) {
      wsRef.current.destroy()
      wsRef.current = null
    }
    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: 'var(--color-border-strong, #94a3b8)',
      progressColor: 'var(--color-primary, #6366f1)',
      cursorColor: 'transparent',
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      height: 48,
      normalize: true,
    })
    wsRef.current = ws
    return ws
  }, [containerRef])

  const destroy = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.destroy()
      wsRef.current = null
    }
  }, [])

  return { wsRef, create, destroy }
}

export function PronunciationExerciseBlock({ targetText, language }: PronunciationExerciseBlockProps) {
  const intl = useIntl()
  const safeText = typeof targetText === 'string' ? targetText : ''
  const safeLang = typeof language === 'string' ? language : 'es'

  const [state, setState] = useState<ExerciseState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [micError, setMicError] = useState<string | null>(null)

  const targetContainerRef = useRef<HTMLDivElement | null>(null)
  const userContainerRef = useRef<HTMLDivElement | null>(null)
  const targetBlobRef = useRef<Blob | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)

  const targetWs = useWaveSurfer(targetContainerRef)
  const userWs = useWaveSurfer(userContainerRef)

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      targetWs.destroy()
      userWs.destroy()
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop())
      }
    }
  }, [targetWs, userWs])

  const handleListen = useCallback(async () => {
    setState('listening')
    setError(null)

    try {
      let blob = targetBlobRef.current
      if (!blob) {
        const res = await fetch(`${BASE}/tts/synthesize`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: safeText, voice: 'default', language: safeLang }),
        })
        if (!res.ok) throw new Error('TTS request failed')
        blob = await res.blob()
        targetBlobRef.current = blob
      }

      const ws = targetWs.create()
      if (!ws) {
        setState('idle')
        return
      }

      const url = URL.createObjectURL(blob)
      ws.load(url)

      ws.on('ready', () => {
        ws.play()
      })

      ws.on('finish', () => {
        setState('idle')
        URL.revokeObjectURL(url)
      })

      ws.on('error', () => {
        setState('idle')
        setError(intl.formatMessage({ id: 'pronunciation.audioError' }))
        URL.revokeObjectURL(url)
      })
    } catch {
      setState('idle')
      setError('Audio no disponible')
    }
  }, [safeText, safeLang, targetWs])

  const handleRecord = useCallback(async () => {
    setMicError(null)
    setError(null)

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      const recorder = new MediaRecorder(stream)
      mediaRecorderRef.current = recorder
      chunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        stream.getTracks().forEach((t) => t.stop())
        streamRef.current = null

        // Show user waveform
        const ws = userWs.create()
        if (ws) {
          const url = URL.createObjectURL(blob)
          ws.load(url)
          ws.on('error', () => URL.revokeObjectURL(url))
        }

        setState('comparing')
      }

      recorder.start()
      setState('recording')
    } catch {
      setMicError(intl.formatMessage({ id: 'pronunciation.micError' }))
      setState('idle')
    }
  }, [userWs])

  const handleStopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop()
    }
  }, [])

  const handlePlayUser = useCallback(() => {
    if (userWs.wsRef.current) {
      userWs.wsRef.current.playPause()
    }
  }, [userWs])

  const handlePlayTarget = useCallback(() => {
    if (targetWs.wsRef.current) {
      targetWs.wsRef.current.playPause()
    }
  }, [targetWs])

  const handleReset = useCallback(() => {
    userWs.destroy()
    setState('idle')
  }, [userWs])

  return (
    <div data-no-explain="" className={`${INLINE_SURFACE} bg-bg-subtle`}>
      <p className={BLOCK_TITLE}>{intl.formatMessage({ id: 'pronunciation.title' })}</p>

      {/* Target text display */}
      <div className="mb-4 p-3 rounded-lg border border-border bg-bg">
        <p className="text-sm text-text leading-relaxed">{safeText}</p>
        {safeLang && (
          <span className="text-xs text-text-muted mt-1 block">{intl.formatMessage({ id: 'pronunciation.language' }, { lang: safeLang })}</span>
        )}
      </div>

      {/* Escucha section */}
      <div className="mb-4">
        <p className="text-xs font-medium text-text-secondary mb-2">{intl.formatMessage({ id: 'pronunciation.listenSection' })}</p>
        <div className="flex items-center gap-3 mb-2">
          <Button
            size="sm"
            onClick={state === 'idle' || state === 'comparing' ? handleListen : handlePlayTarget}
            disabled={state === 'recording'}
          >
            {state === 'listening' ? intl.formatMessage({ id: 'pronunciation.playing' }) : intl.formatMessage({ id: 'pronunciation.listen' })}
          </Button>
        </div>
        <div
          ref={targetContainerRef}
          className="rounded-md overflow-hidden min-h-[48px] bg-bg"
        />
      </div>

      {/* Practica section */}
      <div>
        <p className="text-xs font-medium text-text-secondary mb-2">{intl.formatMessage({ id: 'pronunciation.practiceSection' })}</p>
        <div className="flex items-center gap-3 mb-2">
          {state !== 'recording' ? (
            <Button
              size="sm"
              variant={state === 'comparing' ? 'secondary' : 'primary'}
              onClick={handleRecord}
              disabled={state === 'listening'}
            >
              {state === 'comparing' ? intl.formatMessage({ id: 'pronunciation.reRecord' }) : intl.formatMessage({ id: 'pronunciation.record' })}
            </Button>
          ) : (
            <Button size="sm" variant="danger" onClick={handleStopRecording}>
              {intl.formatMessage({ id: 'pronunciation.stop' })}
            </Button>
          )}
          {state === 'comparing' && (
            <>
              <Button size="sm" variant="secondary" onClick={handlePlayUser}>
                {intl.formatMessage({ id: 'pronunciation.play' })}
              </Button>
              <Button size="sm" variant="ghost" onClick={handleReset}>
                {intl.formatMessage({ id: 'pronunciation.reset' })}
              </Button>
            </>
          )}
        </div>

        {/* Recording indicator */}
        <AnimatePresence>
          {state === 'recording' && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: duration.fast, ease: ease.base }}
              className="flex items-center gap-2 mb-2 text-xs text-danger"
            >
              <span className="h-2 w-2 rounded-full bg-danger animate-pulse" />
              {intl.formatMessage({ id: 'pronunciation.recording' })}
            </motion.div>
          )}
        </AnimatePresence>

        <div
          ref={userContainerRef}
          className="rounded-md overflow-hidden min-h-[48px] bg-bg"
        />
      </div>

      {/* Error messages */}
      <AnimatePresence>
        {(error || micError) && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: duration.fast, ease: ease.base }}
            className="mt-3 text-xs text-danger"
            role="alert"
          >
            {error || micError}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
