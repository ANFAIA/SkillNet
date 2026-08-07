import { motion, AnimatePresence } from 'framer-motion'
import { duration, ease } from '../../../lib/motion'

export interface LessonBuddyProps {
  /** Which step we're on — drives the message. */
  stepIndex: number
  /** Total steps in the lesson. */
  totalSteps: number
  /** Optional custom message (from AI tutor in the future). */
  message?: string
}

/** Contextual messages by step position. Placeholder until the real tutor is wired. */
function defaultMessage(stepIndex: number, totalSteps: number): string {
  if (stepIndex === 0) return 'Veamos de que va esto...'
  if (stepIndex === totalSteps - 1) return 'A ver que tal se te da.'
  return 'Fijate bien en esto.'
}

/**
 * Inline lesson companion — a small avatar + speech bubble that appears
 * on each step of the stepper. Inspired by Brilliant's Koji: proactive,
 * contextual, inside the lesson (not a sidebar chat).
 *
 * v1: static messages based on step position.
 * Future: connected to the tutor AI, sees the component on screen,
 * reacts to correct/incorrect answers, asks guiding questions.
 */
export function LessonBuddy({ stepIndex, totalSteps, message }: LessonBuddyProps) {
  const text = message || defaultMessage(stepIndex, totalSteps)

  return (
    <div className="flex items-start gap-2.5 mb-4">
      {/* Avatar */}
      <motion.div
        className="flex-shrink-0 w-8 h-8 rounded-full bg-bg-subtle border border-border overflow-hidden flex items-center justify-center"
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ duration: duration.normal, ease: [...ease.bounce] }}
      >
        <img
          src="/logo.png"
          alt=""
          className="w-5 h-5"
        />
      </motion.div>

      {/* Speech bubble */}
      <AnimatePresence mode="wait">
        <motion.div
          key={`buddy-${stepIndex}`}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: duration.normal, ease: [...ease.base] }}
          className="text-sm text-text-secondary leading-relaxed"
        >
          {text}
        </motion.div>
      </AnimatePresence>
    </div>
  )
}
