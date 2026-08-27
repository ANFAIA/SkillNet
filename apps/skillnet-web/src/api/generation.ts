import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { get } from './client'
import type { GenerationJob, GenerationProgress, GenerationStep } from '../types'

// Map a polled GenerationJob (REST) to the normalized progress shape used by
// the GenerationProgress component.
export function jobToProgress(job: GenerationJob): GenerationProgress {
  return {
    step: job.status,
    courseId: job.result_course_id ?? undefined,
    error: job.error_message ?? undefined,
  }
}

// Primary tracking: SSE. Falls back gracefully — `connectionFailed` lets the
// UI switch to REST polling via useGenerationJobStatus.
export function useGenerationProgress(jobId: string | null) {
  const [progress, setProgress] = useState<GenerationProgress>({ step: 'pending' })
  const [isActive, setIsActive] = useState(false)
  const [connectionFailed, setConnectionFailed] = useState(false)

  useEffect(() => {
    if (!jobId) return

    setIsActive(true)
    setConnectionFailed(false)
    const controller = new AbortController()
    // Did a terminal event (`completed` / `error`) actually arrive? A stream that ends
    // without one has not told us the outcome, however cleanly it ended.
    let sawTerminal = false

    async function connect() {
      try {
        const res = await fetch(`/api/v1/generation-jobs/${jobId}/progress`, {
          credentials: 'include',
          signal: controller.signal,
        })

        if (!res.ok || !res.body) throw new Error(`SSE failed: ${res.status}`)

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let eventType = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''

          for (const line of lines) {
            if (line.startsWith('event:')) {
              eventType = line.slice(6).trim()
            } else if (line.startsWith('data:')) {
              const raw = line.slice(5).trim()
              if (!raw) continue
              let data: Record<string, unknown>
              try {
                data = JSON.parse(raw)
              } catch {
                continue
              }

              if (eventType === 'step' || eventType === 'progress') {
                setProgress((prev) => ({
                  ...prev,
                  step: (data.step as GenerationStep) ?? prev.step,
                  message: (data.message as string) ?? prev.message,
                }))
              } else if (eventType === 'review_result') {
                setProgress((prev) => ({
                  ...prev,
                  message: (data.message as string) ?? prev.message,
                }))
              } else if (eventType === 'completed') {
                sawTerminal = true
                setProgress({
                  step: 'published',
                  courseId: (data.course_id as string) ?? (data.courseId as string),
                })
                setIsActive(false)
              } else if (eventType === 'error') {
                sawTerminal = true
                setProgress({
                  step: 'failed',
                  error:
                    (data.message as string) ??
                    (data.detail as string) ??
                    (data.error as string) ??
                    'Generation failed',
                })
                setIsActive(false)
              }

              eventType = ''
            }
          }
        }
        // The reader is done. If no terminal event ever arrived, the stream was closed
        // *for* us — an idle proxy timeout (`docker/nginx.conf` closes at 300s), a
        // redeployed API, a dropped connection — and the job may well have finished
        // meanwhile. This used to return normally with `connectionFailed` still false,
        // so the polling fallback below (gated on it) never started and the screen froze
        // on the last step it had seen even though the server was done.
        if (!sawTerminal && !controller.signal.aborted) setConnectionFailed(true)
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          // Let the UI fall back to polling instead of hard-failing.
          setConnectionFailed(true)
        }
      }
    }

    connect()
    return () => controller.abort()
  }, [jobId])

  return { progress, isActive, connectionFailed }
}

// Fallback: poll the generation job status via REST until terminal.
export function useGenerationJobStatus(jobId: string | null) {
  return useQuery({
    queryKey: ['generation-jobs', jobId],
    queryFn: () => get<GenerationJob>(`/generation-jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === 'published' || status === 'failed') return false
      return 3000
    },
  })
}
