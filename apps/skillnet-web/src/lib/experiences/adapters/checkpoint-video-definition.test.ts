import { describe, expect, it } from 'vitest'

import { validateCheckpointVideoDefinition } from './checkpoint-video-definition'

describe('validateCheckpointVideoDefinition', () => {
  it('accepts same-origin media with a transcript instead of captions', () => {
    expect(validateCheckpointVideoDefinition({
      src: '/assets/checkpoint.mp4',
      transcript: 'Contenido equivalente del vídeo.',
    })).toMatchObject({
      ok: true,
      definition: { src: '/assets/checkpoint.mp4', title: 'Vídeo formativo' },
    })
  })

  it.each([
    { src: '/assets/checkpoint.mp4' },
    { src: '//tracker.invalid/video.mp4', transcript: 'Texto' },
    { src: 'http://example.com/video.mp4', transcript: 'Texto' },
    { src: 'data:video/mp4;base64,AAAA', transcript: 'Texto' },
    { src: '/assets/checkpoint.mp4', captionsSrc: 'javascript:alert(1)' },
  ])('rejects unsafe or inaccessible definitions', (definition) => {
    expect(validateCheckpointVideoDefinition(definition)).toEqual({ ok: false })
  })
})
