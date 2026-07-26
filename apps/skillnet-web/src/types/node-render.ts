// Runtime contract of a node render (§5.2 / §11.3).
//
// This file used to be `ui-spec.ts` and used to describe the flat JSON IR the
// browser received. It no longer does: since the frontend renders the dialect
// with OpenUI's own runtime, the IR never crosses the wire as JSON — the browser
// receives the program re-serialized from the validated `UISpec` as **text**, and
// the component/prop contract lives in
// `src/components/courses/kit/schemas.ts` as zod schemas.
//
// What is left here is the part that was never about the IR: the answer endpoint
// `QuizItemBlock` posts to, and the `ui_format` enum the node view surfaces.

/** `ui_format` enum — mirrors `UiFormat` in `src/models/node_render.py`. */
export type UiFormat = 'explanation' | 'simulation' | 'exercise' | 'chart' | 'mixed'

/** Type-specific answer payloads accepted by `POST /nodes/{node_id}/answer`. */
export type NodeAnswerPayload =
  | { selected: number }
  | { answer: boolean }
  | { answers: string[] }
  | { response: string }

export interface NodeAnswerRequest {
  render_id: string
  item_id: string
  answer: NodeAnswerPayload
  /**
   * INFORMATIVE ONLY — the server must not trust this number (§7.4, §11.3).
   *
   * It decides whether the correct answer is revealed (`correct_answer` below is
   * populated once the hint quota is spent), so a value the client chooses cannot
   * govern it: anybody can POST `hints_used: 3` and be handed the answer without
   * having asked for a single hint. The count of record is
   * `node_attempts.hints_used` for `(user_id, node_id, item_id)`, which only
   * `POST /nodes/{id}/hint` increments. B5/B9 must derive the number server-side
   * and treat this field as telemetry (or drop it from the contract).
   *
   * `QuizItemBlock` grants no hints, so it always reports `0`.
   */
  hints_used: number
  latency_ms: number
}

export interface NodeAttemptResult {
  score: number
  passed: boolean
  feedback: string
  /**
   * Only present once the item is passed or the hint quota is spent. "Spent" is
   * counted from `node_attempts.hints_used` on the server, never from the
   * `hints_used` this client sent — see `NodeAnswerRequest.hints_used`.
   */
  correct_answer: Record<string, unknown> | null
  mastery: number
  state: string
  consecutive_correct: number
  consecutive_failed: number
  next: 'retry' | 'next_item' | 'next_node'
}
