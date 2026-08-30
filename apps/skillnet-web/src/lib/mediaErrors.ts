/**
 * What a failed artifact says, in the reader's language.
 *
 * The server already decided this contract and wrote it down in
 * `services/media/jobs.py`: every failure carries a stable **code**, and the sentence
 * beside it is "short, safe and English" — a fallback for whoever has no UI, not copy for
 * one. The SPA was rendering that sentence verbatim, so a learner reading a course in
 * Spanish was told "This generation failed. The details are in the server log."
 *
 * The wording lives here, once, keyed by code. A code this table does not know falls back
 * to the generic sentence rather than to the server's text: an unknown code means the
 * backend grew a case the UI has not been taught, and showing English prose is not a
 * better answer than showing the honest generic one.
 */

const MESSAGE_ID_BY_CODE: Record<string, string> = {
  llm_failed: 'mediaError.llmFailed',
  provider_quota: 'mediaError.providerQuota',
  provider_down: 'mediaError.providerDown',
  cancelled: 'mediaError.cancelled',
  no_context: 'mediaError.noContext',
  internal_error: 'mediaError.internal',
  asset_missing: 'mediaError.assetMissing',
}

/** The generic sentence — for no code, and for one this build does not know. */
export const MEDIA_ERROR_FALLBACK_ID = 'mediaError.internal'

export function mediaErrorMessageId(code: string | null | undefined): string {
  if (!code) return MEDIA_ERROR_FALLBACK_ID
  return MESSAGE_ID_BY_CODE[code] ?? MEDIA_ERROR_FALLBACK_ID
}
