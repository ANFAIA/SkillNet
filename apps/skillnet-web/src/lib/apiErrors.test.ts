/**
 * A rejected request has to speak the reader's language.
 *
 * The API's envelope splits the two halves on purpose: `code` is stable, `detail` is
 * English prose for a caller with no UI (`core/exceptions.py`). The SPA was rendering
 * `detail`, so a Spanish learner hitting a 409 read an English sentence.
 *
 * The fallback direction is the part worth pinning down: an unmapped code keeps the
 * server's sentence rather than becoming "something went wrong", because a
 * `VALIDATION_ERROR` message is written at the raise site and is the only actionable part
 * of the answer.
 */
import { createIntl } from 'react-intl'
import { describe, expect, it } from 'vitest'

import { apiErrorMessage, apiErrorMessageId } from './apiErrors'
import { ApiError } from '../api/client'
import { en } from '../i18n/en'
import { es } from '../i18n/es'

/** Every code the SPA maps. Mirrors the table in `apiErrors.ts`. */
const MAPPED_CODES = [
  'NOT_FOUND',
  'INTERNAL_ERROR',
  'REQUEST_TIMEOUT',
  'INVALID_RESPONSE',
  'RATE_LIMITED',
  'PAYLOAD_TOO_LARGE',
  'SOURCE_GENERATION_FAILED',
  'TTS_DISABLED',
  'GOOGLE_AUTH_ERROR',
  'media_no_context',
]

const intlEs = createIntl({ locale: 'es', messages: es, defaultLocale: 'es' })

describe('apiErrorMessageId', () => {
  it.each(MAPPED_CODES)('gives %s a sentence in both languages', (code) => {
    const id = apiErrorMessageId(code)
    expect(id).toBe(`error.${code}`)
    expect(es).toHaveProperty(id as string)
    expect(en).toHaveProperty(id as string)
  })

  it('has nothing for no code, or one this build does not know', () => {
    for (const absent of [null, undefined, '', 'A_CODE_FROM_A_NEWER_SERVER']) {
      expect(apiErrorMessageId(absent)).toBeNull()
    }
  })
})

describe('apiErrorMessage', () => {
  it('translates a mapped code and never shows the server text', () => {
    const error = new ApiError(404, { detail: 'Course with id 7 not found', code: 'NOT_FOUND' })
    expect(apiErrorMessage(intlEs, error, 'error.description')).toBe(es['error.NOT_FOUND'])
  })

  it('keeps the server sentence for a code it does not map', () => {
    // Including the deliberately unmapped catch-alls: their message is written at the
    // raise site and is the only actionable part of the answer.
    for (const code of ['A_NEW_CODE', 'CONFLICT', 'VALIDATION_ERROR', 'FORBIDDEN', 'LLM_ERROR']) {
      const error = new ApiError(422, { detail: 'Email already registered', code })
      expect(apiErrorMessage(intlEs, error, 'error.description')).toBe('Email already registered')
    }
  })

  it('uses the caller fallback for anything that is not an ApiError', () => {
    for (const other of [new TypeError('boom'), null, undefined, 'nope']) {
      expect(apiErrorMessage(intlEs, other, 'error.description')).toBe(es['error.description'])
    }
  })

  it('uses the caller fallback when the server sent no sentence either', () => {
    const error = new ApiError(500, { detail: '   ' })
    expect(apiErrorMessage(intlEs, error, 'error.description')).toBe(es['error.description'])
  })
})
