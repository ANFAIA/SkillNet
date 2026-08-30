/**
 * A failed artifact has to speak the reader's language.
 *
 * The bug this locks out: the SPA rendered the server's `error` sentence verbatim, so a
 * course being read in Spanish said "This generation failed. The details are in the
 * server log." The server never meant that text as copy — `services/media/jobs.py` says
 * so in as many words — it means the code beside it.
 */
import { describe, expect, it } from 'vitest'

import { MEDIA_ERROR_FALLBACK_ID, mediaErrorMessageId } from './mediaErrors'
import { es } from '../i18n/es'
import { en } from '../i18n/en'

/** Every code `services/media/jobs.py` can put on a row. Mirrors that module. */
const BACKEND_CODES = [
  'llm_failed',
  'provider_quota',
  'provider_down',
  'cancelled',
  'no_context',
  'internal_error',
  'asset_missing',
]

describe('mediaErrorMessageId', () => {
  it.each(BACKEND_CODES)('gives %s a sentence in both languages', (code) => {
    const id = mediaErrorMessageId(code)
    expect(es).toHaveProperty(id)
    expect(en).toHaveProperty(id)
    // Not the generic one: each code exists because it says something the others do not.
    expect(id).not.toBe(code === 'internal_error' ? '' : MEDIA_ERROR_FALLBACK_ID)
  })

  it('says something honest when there is no code, or one this build does not know', () => {
    for (const absent of [null, undefined, '', 'a_code_from_a_newer_server']) {
      expect(mediaErrorMessageId(absent)).toBe(MEDIA_ERROR_FALLBACK_ID)
    }
    expect(es[MEDIA_ERROR_FALLBACK_ID]).toBeTruthy()
    expect(en[MEDIA_ERROR_FALLBACK_ID]).toBeTruthy()
  })

  it('never hands back the English sentence the server sent', () => {
    // The whole point: the value is a message id the UI owns, never server text.
    for (const code of BACKEND_CODES) {
      expect(mediaErrorMessageId(code)).toMatch(/^mediaError\./)
    }
  })
})
