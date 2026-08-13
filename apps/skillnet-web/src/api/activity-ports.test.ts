import { afterEach, describe, expect, it, vi } from 'vitest'

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
