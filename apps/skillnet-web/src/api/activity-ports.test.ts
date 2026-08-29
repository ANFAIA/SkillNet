import { afterEach, describe, expect, it, vi } from 'vitest'

import { ActivityNotEvaluableError } from '../lib/didact'
import type { DidactEvent } from '../lib/didact'
import { createActivityHostPorts } from './activity-ports'

afterEach(() => vi.restoreAllMocks())

describe('createActivityHostPorts events', () => {
  it('posts the closed versioned envelope to the activity-scoped endpoint', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))
    const event: DidactEvent = {
      version: 1,
      eventId: '9f2041a3-cbec-4517-bae8-c3013e5da414',
      activityId: 'ac26a33d-e1a9-4d99-868c-ef87d073c978',
      componentId: 'didact.measurement-lab',
      type: 'answered',
      occurredAt: '2026-08-13T05:00:00.000Z',
      scope: { organizationId: 'must-not-cross-wire', courseId: 'also-server-owned' },
      payload: {
        attemptId: '7f298982-08af-4078-af04-b0b025c9074e',
        outcome: 'correct',
        score: 0.75,
        durationMs: 1200,
      },
    }

    await createActivityHostPorts(event.activityId).events?.emit(event)

    expect(fetch).toHaveBeenCalledOnce()
    const [url, request] = fetch.mock.calls[0]
    expect(url).toBe(`/api/v1/activities/${event.activityId}/events`)
    expect(JSON.parse(String(request?.body))).toEqual({
      version: 1,
      event_id: event.eventId,
      activity_id: event.activityId,
      component_id: event.componentId,
      type: 'answered',
      occurred_at: event.occurredAt,
      payload: {
        attempt_id: event.payload?.attemptId,
        outcome: 'correct',
        score: 0.75,
        duration_ms: 1200,
      },
    })
  })

  it('drops fields outside the telemetry allowlist before transport', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(null, { status: 204 }))
    const event = {
      version: 1,
      eventId: '9f2041a3-cbec-4517-bae8-c3013e5da414',
      activityId: 'ac26a33d-e1a9-4d99-868c-ef87d073c978',
      componentId: 'didact.measurement-lab',
      type: 'attempted',
      occurredAt: '2026-08-13T05:00:00.000Z',
      scope: { organizationId: '', courseId: '' },
      payload: { response: 'free text', solution: 'secret' },
    } as unknown as DidactEvent

    await createActivityHostPorts(event.activityId).events?.emit(event)

    const body = JSON.parse(String(fetch.mock.calls[0][1]?.body))
    expect(body.payload).toEqual({})
    expect(JSON.stringify(body)).not.toContain('free text')
    expect(JSON.stringify(body)).not.toContain('secret')
  })
})

describe('createActivityHostPorts evaluation', () => {
  const request = {
    scope: { organizationId: '', courseId: '' },
    componentId: 'didact.quiz.single-choice',
    attemptId: '7f298982-08af-4078-af04-b0b025c9074e',
    response: { answer: 'a' },
  } as const

  it('uses the atomic neutral attempt endpoint when the binding is fixed', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      outcome: 'correct',
      score: 1,
      result: { feedback: 'Bien' },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

    const result = await createActivityHostPorts('definition-id', {
      bindingId: 'binding-id',
    }).evaluation?.evaluate(request)

    expect(fetch.mock.calls[0][0]).toBe('/api/v1/activities/definition-id/attempts')
    expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({
      attempt_id: request.attemptId,
      binding_id: 'binding-id',
      submission: request.response,
    })
    expect(result).toEqual({ outcome: 'correct', score: 1, feedback: 'Bien' })
  })

  it('keeps historical activities on the legacy evaluate endpoint', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      status: 'completed',
      result: { outcome: 'partial', score: 0.5, feedback: 'Revisa' },
      decline_reason: null,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

    await createActivityHostPorts('activity-id').evaluation?.evaluate(request)

    expect(fetch.mock.calls[0][0]).toBe('/api/v1/activities/activity-id/evaluate')
    expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual({
      submission: request.response,
    })
  })

  /**
   * The signal that reached the browser and got thrown away.
   *
   * `result` carries more than `feedback`: the server's decision to close the item
   * (`show_worked_solution`), the solution it wrote for it, and the mastery it recorded.
   * The port used to pick `feedback` out and drop the rest, so a worked solution the
   * server had already produced could never be painted — the bug looked like a missing
   * backend feature and was a missing four lines here.
   */
  it('keeps the whole envelope, not just the feedback, on the attempt endpoint', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      outcome: 'incorrect',
      score: 0,
      result: {
        feedback: 'Revisa el orden',
        show_worked_solution: true,
        state: 'learning',
        mastery: 0.25,
        consecutive_failed: 4,
        solution: { solution: 'Primero, después, por último', explanation: 'Va por criticidad.' },
      },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

    const result = await createActivityHostPorts('definition-id', {
      bindingId: 'binding-id',
    }).evaluation?.evaluate(request)

    expect(result).toEqual({
      outcome: 'incorrect',
      score: 0,
      feedback: 'Revisa el orden',
      showWorkedSolution: true,
      state: 'learning',
      mastery: 0.25,
      solution: { solution: 'Primero, después, por último', explanation: 'Va por criticidad.' },
    })
  })

  it('also reads the envelope off the legacy evaluate endpoint', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      status: 'completed',
      result: {
        outcome: 'incorrect',
        score: 0,
        show_worked_solution: true,
        solution: { solution: 'Cada mes', explanation: null },
      },
      decline_reason: null,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

    const result = await createActivityHostPorts('activity-id').evaluation?.evaluate(request)

    expect(result).toMatchObject({
      outcome: 'incorrect',
      showWorkedSolution: true,
      solution: { solution: 'Cada mes', explanation: null },
    })
  })

  it('ignores a solution that is not written out: the client never assembles one', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      outcome: 'incorrect',
      score: 0,
      result: { show_worked_solution: true, solution: { correct_order: [1, 0] } },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

    const result = await createActivityHostPorts('definition-id', {
      bindingId: 'binding-id',
    }).evaluation?.evaluate(request)

    expect(result).toEqual({ outcome: 'incorrect', score: 0, showWorkedSolution: true })
  })

  /**
   * "This cannot be graded" is not "this failed": one is worth another attempt and the
   * other never will be. Both evaluation paths word it differently, and both have to end
   * up as the same error, or the learner is offered a retry that leads nowhere.
   */
  it('turns a declined evaluation into ActivityNotEvaluableError', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      status: 'declined',
      result: null,
      decline_reason: 'activity has no answer key',
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

    await expect(
      createActivityHostPorts('activity-id').evaluation?.evaluate(request),
    ).rejects.toBeInstanceOf(ActivityNotEvaluableError)
  })

  it('turns the attempt endpoint 422 into the same error', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      detail: 'activity cannot be evaluated: unsupported component',
      field: 'submission',
    }), { status: 422, headers: { 'Content-Type': 'application/json' } }))

    await expect(
      createActivityHostPorts('definition-id', { bindingId: 'binding-id' }).evaluation?.evaluate(request),
    ).rejects.toBeInstanceOf(ActivityNotEvaluableError)
  })

  it('leaves any other failure alone, so it stays retryable', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      detail: 'Internal Server Error',
    }), { status: 500, headers: { 'Content-Type': 'application/json' } }))

    const failure = await createActivityHostPorts('definition-id', { bindingId: 'binding-id' })
      .evaluation?.evaluate(request)
      .catch((error: unknown) => error)

    expect(failure).not.toBeInstanceOf(ActivityNotEvaluableError)
  })
})

describe('createActivityHostPorts assets', () => {
  it('resolves opaque references through the activity endpoint without client scope', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      ref: 'skasset_opaque',
      url: '/api/v1/media/artifacts/asset-id/asset',
      mime_type: 'image/png',
      alt: 'Diagrama accesible',
      long_description: 'Descripción larga',
      width: 1200,
      height: 800,
      duration_ms: null,
      transcript: null,
      captions: null,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

    const result = await createActivityHostPorts('activity-id').assets?.resolve(
      'skasset_opaque',
      { organizationId: 'spoofed-org', courseId: 'spoofed-course' },
    )

    expect(fetch.mock.calls[0][0]).toBe(
      '/api/v1/activities/activity-id/assets/skasset_opaque',
    )
    expect(fetch.mock.calls[0][1]?.body).toBeUndefined()
    expect(result).toMatchObject({
      ref: 'skasset_opaque',
      mimeType: 'image/png',
      alt: 'Diagrama accesible',
      width: 1200,
      height: 800,
    })
    expect(JSON.stringify(result)).not.toContain('path')
  })
})

describe('createActivityHostPorts progress', () => {
  it('reads server-owned progress and refuses client writes', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      component_id: 'didact.progress',
      status: 'in_progress',
      progress: 42,
      level: 'intermediate',
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    const ports = createActivityHostPorts('activity-id')

    const record = await ports.progress?.read(
      { organizationId: 'spoofed', courseId: 'spoofed' },
      'didact.progress',
    )

    expect(fetch.mock.calls[0][0]).toBe('/api/v1/activities/activity-id/progress')
    expect(record).toMatchObject({
      componentId: 'didact.progress',
      status: 'in_progress',
      progress: 42,
      evidence: { level: 'intermediate' },
    })
    await expect(ports.progress?.write({
      scope: { organizationId: '', courseId: '' },
      componentId: 'didact.progress',
      status: 'completed',
      progress: 100,
    })).rejects.toThrow('progress_is_server_owned')
    expect(fetch).toHaveBeenCalledOnce()
  })
})
