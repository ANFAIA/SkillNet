/**
 * What a failed request says, in the reader's language.
 *
 * The API's error envelope is `{detail, code, field, details?}` and the contract behind it
 * (`apps/skillnet-api/src/core/exceptions.py`, plus the handlers in `main.py`) is explicit
 * about which half is which: **`code` is stable and machine-readable, `detail` is English
 * prose meant as a fallback for a caller with no UI**. The SPA was rendering `detail`
 * verbatim in about twenty places, so a Spanish learner who hit a 409 was told
 * "Enrollment already exists for this course".
 *
 * The wording lives here, once, keyed by code — the same shape as `mediaErrors.ts`, for
 * the same reason.
 *
 * **Only codes whose backend message is a constant are mapped.** That line is the whole
 * design. `CONFLICT`, `VALIDATION_ERROR`, `FORBIDDEN` and `LLM_ERROR` are catch-alls: the
 * backend raises them from 36, 65, 23 and 27 sites respectively, each with its own
 * sentence, and "Email already registered" or "You can only view your own enrolments" is
 * the only actionable part of the answer. Replacing those with one generic line per code
 * would be a localised regression, so they are left to fall through to `detail`.
 *
 * An unmapped code therefore keeps the server's English sentence — the opposite of
 * `mediaErrors.ts`, which falls back to a generic id. A media job has a closed set of
 * failure reasons, so an unknown one really is a gap in the table; the REST surface has no
 * such closed set. And when the server sent no sentence either, the caller's own
 * `fallbackId` takes over, which is better copy than a generic code line anyway: it is
 * written for the screen the user is looking at.
 *
 * Deliberately **not** here:
 *
 * - `capability_blocked`, which has its own role-aware copy in `capabilityCopy.ts`. Its
 *   `details.capability` / `details.reason` say far more than one sentence per code could.
 * - The `RENDER_*` codes. They are the render layer telling an operator that a build
 *   artefact is missing or unparseable, and the node pipeline consumes them internally on
 *   its repair path; they are not sentences shown to somebody reading a course.
 */
import type { IntlShape } from 'react-intl'

import { ApiError } from '../api/client'

/**
 * Every code the SPA can actually put in front of somebody. Mirrors the raise sites in
 * `apps/skillnet-api/src/` — do not add a code here that the backend does not send.
 */
const MESSAGE_ID_BY_CODE: Record<string, string> = {
  // core/exceptions.py + main.py handlers. `NotFoundError` composes its message from the
  // resource name and a raw uuid, and `unhandled_error_handler` sends one fixed string,
  // so for these two the catalogue says more than the wire does.
  NOT_FOUND: 'error.NOT_FOUND',
  INTERNAL_ERROR: 'error.INTERNAL_ERROR',
  // The two codes the frontend raises itself, in `api/client.ts`: a request that outran
  // its timeout, and a 2xx whose body is not JSON — which is what a reverse proxy that
  // forgot the `/api` route looks like from in here (see CLAUDE.md on Dokploy).
  REQUEST_TIMEOUT: 'error.REQUEST_TIMEOUT',
  INVALID_RESPONSE: 'error.INVALID_RESPONSE',
  // services/explain_service.py
  RATE_LIMITED: 'error.RATE_LIMITED',
  // services/document_service.py
  PAYLOAD_TOO_LARGE: 'error.PAYLOAD_TOO_LARGE',
  SOURCE_GENERATION_FAILED: 'error.SOURCE_GENERATION_FAILED',
  // routes/tts.py
  TTS_DISABLED: 'error.TTS_DISABLED',
  // services/google_oauth.py
  GOOGLE_AUTH_ERROR: 'error.GOOGLE_AUTH_ERROR',
  // services/media/subject.py — lower-case, like `capability_blocked`, because that is
  // the string the media contract was written around. See the note in exceptions.py.
  media_no_context: 'error.media_no_context',
}

/** The id for an API error code, or `null` when this build has no copy for it. */
export function apiErrorMessageId(code: string | null | undefined): string | null {
  if (!code) return null
  return MESSAGE_ID_BY_CODE[code] ?? null
}

/**
 * The sentence to show for a rejected request.
 *
 * In order: the copy for the error's `code`, then the server's own `detail`, then
 * `fallbackId` — which is where anything that is not an `ApiError` at all (a thrown
 * `TypeError`, an aborted fetch) lands.
 */
export function apiErrorMessage(intl: IntlShape, error: unknown, fallbackId: string): string {
  const api = error instanceof ApiError ? error : null

  const id = apiErrorMessageId(api?.body.code)
  if (id && intl.messages[id]) return intl.formatMessage({ id })

  const detail = api?.body.detail?.trim()
  if (detail) return detail

  return intl.formatMessage({ id: fallbackId })
}
