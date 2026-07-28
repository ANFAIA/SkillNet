import { useMemo, useRef } from 'react'
import { UiSpecRenderer } from '../courses/UiSpecRenderer'
import { gateProgram } from '../courses/kit'
import { ChatMarkdown } from './ChatMarkdown'
import type { ChatMessage } from '../../types'

/** `ui_format` the tutor lays chat answers out in — `CHAT_UI_FORMAT` in `chat_service.py`. */
const CHAT_UI_FORMAT = 'explanation'

export interface ChatAnswerProps {
  message: ChatMessage
}

/**
 * One assistant answer: the kit program if there is one, the prose if there is not.
 *
 * ## Two beats, one bubble
 *
 * The tutor answers twice over the same connection (`api/chat.ts`): prose first, and
 * then — for an answer long enough to earn a second call — the *same* answer
 * re-expressed in the SkillNet kit. `done` fires between the two on purpose, so the
 * composer comes back while the layout is still being produced.
 *
 * The prose is therefore the **streaming phase**, not a second copy of the answer. It
 * is what the learner reads for the two seconds the layout takes, and it stops
 * existing the moment blocks can take its place. Rendering both would say the tutor
 * answered twice; rendering blocks *under* the prose would make the bubble grow past
 * the viewport at the exact moment the learner finished reading it.
 *
 * ## Why the program is gated here and not only inside `UiSpecRenderer`
 *
 * Because `UiSpecRenderer` answers "may this be painted?" with `null`, and `null` in a
 * chat bubble is not a degraded answer — it is a **blank bubble**, with the prose
 * already thrown away. The server validating a program is not enough to rule that out:
 * the browser's gate is deliberately the stricter of the two (it unions two parsers
 * that disagree on duplicate ids, caps the *painted* element count rather than the
 * statement count, and fails closed on a parse exception), so a server-valid program
 * can still be refused here. Asking the gate first turns every one of those cases back
 * into the prose the learner was already reading.
 *
 * Both gate passes are `useMemo`'d on the same string and the parser is pure, so this
 * costs one extra parse of ~1 KB, once, on the frame the program lands.
 */
export function ChatAnswer({ message }: ChatAnswerProps) {
  const gate = useMemo(() => gateProgram(message.program), [message.program])
  const showBlocks = Boolean(message.program) && !gate.blocked && !gate.empty

  /**
   * Did the learner watch the prose, or was the program already there on the first
   * frame? Same distinction `NodeView` draws with `viewingHeld`, and for the same
   * reason: blocks that replace something the learner was reading should resolve in;
   * a bubble rehydrated from history with its program attached must paint at once,
   * because animating on load is the anti-pattern the motion system names outright.
   *
   * `StackBlock` is what consumes this, and it already drops the stagger for
   * `useReducedMotion()` — OS setting *or* the preference declared in the wizard.
   */
  const watchedProse = useRef(!message.program)

  if (showBlocks) {
    return (
      <UiSpecRenderer
        program={message.program ?? null}
        // No node owns a chat answer, and no `renderId` either: the layout prompt
        // cannot emit `QuizItem`, and one that appeared anyway must render read-only
        // rather than post an attempt against a node the learner is not in.
        nodeId=""
        format={CHAT_UI_FORMAT}
        arriving={watchedProse.current}
      />
    )
  }

  // While the layout call is in flight, hide the raw markdown and show a
  // placeholder so the learner never sees prose that will be swapped out.
  if (message.isLayingOut) {
    return (
      <span className="typing-dots" aria-label="Preparando formato">
        <span /><span /><span />
      </span>
    )
  }

  return (
    <>
      <ChatMarkdown content={message.content} isStreaming={message.isStreaming} />
      {message.isStreaming && !message.content && (
        <span className="typing-dots" aria-label="Escribiendo">
          <span /><span /><span />
        </span>
      )}
    </>
  )
}
